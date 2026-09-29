import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { deflateSync } from "node:zlib";

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const serverPath = path.join(projectRoot, "src", "index.mjs");

async function withTempDirectory(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "readonly-files-mcp-"));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

function sendRequest(id, method, params) {
  return JSON.stringify({ jsonrpc: "2.0", id, method, params });
}

function createStoredZip(entries) {
  const localRecords = [];
  const centralRecords = [];
  let offset = 0;

  for (const [name, value] of entries) {
    const nameBytes = Buffer.from(name, "utf8");
    const contents = Buffer.isBuffer(value) ? value : Buffer.from(value, "utf8");
    const localHeader = Buffer.alloc(30);
    localHeader.writeUInt32LE(0x04034b50, 0);
    localHeader.writeUInt16LE(20, 4);
    localHeader.writeUInt16LE(0, 6);
    localHeader.writeUInt16LE(0, 8);
    localHeader.writeUInt32LE(contents.length, 18);
    localHeader.writeUInt32LE(contents.length, 22);
    localHeader.writeUInt16LE(nameBytes.length, 26);
    const localRecord = Buffer.concat([localHeader, nameBytes, contents]);
    localRecords.push(localRecord);

    const centralHeader = Buffer.alloc(46);
    centralHeader.writeUInt32LE(0x02014b50, 0);
    centralHeader.writeUInt16LE(20, 4);
    centralHeader.writeUInt16LE(20, 6);
    centralHeader.writeUInt16LE(0, 8);
    centralHeader.writeUInt16LE(0, 10);
    centralHeader.writeUInt32LE(contents.length, 20);
    centralHeader.writeUInt32LE(contents.length, 24);
    centralHeader.writeUInt16LE(nameBytes.length, 28);
    centralHeader.writeUInt32LE(offset, 42);
    centralRecords.push(Buffer.concat([centralHeader, nameBytes]));
    offset += localRecord.length;
  }

  const centralDirectory = Buffer.concat(centralRecords);
  const endRecord = Buffer.alloc(22);
  endRecord.writeUInt32LE(0x06054b50, 0);
  endRecord.writeUInt16LE(entries.length, 8);
  endRecord.writeUInt16LE(entries.length, 10);
  endRecord.writeUInt32LE(centralDirectory.length, 12);
  endRecord.writeUInt32LE(offset, 16);
  return Buffer.concat([...localRecords, centralDirectory, endRecord]);
}

function createCompressedPdf(text) {
  const stream = deflateSync(Buffer.from(`BT /F1 12 Tf (${text}) Tj ET`, "latin1"));
  return Buffer.concat([
    Buffer.from("%PDF-1.4\n1 0 obj\n<< /Length ", "latin1"),
    Buffer.from(String(stream.length), "ascii"),
    Buffer.from(" /Filter /FlateDecode >>\nstream\n", "latin1"),
    stream,
    Buffer.from("\nendstream\nendobj\n%%EOF\n", "latin1")
  ]);
}

function createPngHeader(width, height) {
  const header = Buffer.alloc(24);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(header, 0);
  header.writeUInt32BE(13, 8);
  header.write("IHDR", 12, "ascii");
  header.writeUInt32BE(width, 16);
  header.writeUInt32BE(height, 20);
  return header;
}

function createJpegHeader(width, height) {
  return Buffer.from([
    0xff, 0xd8,
    0xff, 0xc0, 0x00, 0x11, 0x08,
    (height >> 8) & 0xff, height & 0xff,
    (width >> 8) & 0xff, width & 0xff,
    0x03, 0x01, 0x11, 0x00, 0x02, 0x11, 0x00, 0x03, 0x11, 0x00,
    0xff, 0xd9
  ]);
}

test("Excel extraction preserves missing columns instead of shifting values left", async () => {
  await withTempDirectory(async root => {
    await writeFile(path.join(root, "sparse.xlsx"), createStoredZip([
      ["xl/worksheets/sheet1.xml", '<worksheet><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Name</t></is></c><c r="C1"><v>42</v></c></row></sheetData></worksheet>']
    ]));
    const { replies } = await runServer(root, [sendRequest(1, "tools/call", { name: "read_file", arguments: { path: "sparse.xlsx" } })]);
    assert.match(replies[0].result.content[0].text, /Name\t\t42/);
  });
});

test("invalid UTF-8 fails explicitly instead of silently replacing document content", async () => {
  await withTempDirectory(async root => {
    await writeFile(path.join(root, "invalid.txt"), Buffer.from([0xc3, 0x28]));
    const { replies } = await runServer(root, [sendRequest(1, "tools/call", { name: "read_file", arguments: { path: "invalid.txt" } })]);
    assert.equal(replies[0].result.isError, true);
    assert.match(replies[0].result.content[0].text, /UTF-8|encoding/i);
  });
});

test("PDF extraction bounds the total expanded data across multiple streams", async () => {
  await withTempDirectory(async root => {
    const largeStream = deflateSync(Buffer.from(" ".repeat(6 * 1024 * 1024) + "BT (hello) Tj ET"));
    const pdf = Buffer.concat([Buffer.from("%PDF-1.4\n"), ...[1, 2].flatMap(() => [Buffer.from("<< /Filter /FlateDecode >>\nstream\n"), largeStream, Buffer.from("\nendstream\n")])]);
    await writeFile(path.join(root, "large.pdf"), pdf);
    const { replies } = await runServer(root, [sendRequest(1, "tools/call", { name: "read_file", arguments: { path: "large.pdf" } })]);
    assert.equal(replies[0].result.isError, true);
  });
});

async function runServer(root, messages) {
  const child = spawn(process.execPath, [serverPath, "--root", root], {
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true
  });
  let stdout = "";
  let stderr = "";
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => { stdout += chunk; });
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  child.stdin.end(`${messages.join("\n")}\n`);

  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("close", resolve);
  });
  const replies = stdout
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  return { exitCode, stderr, replies };
}

test("lists only files under the explicit allowed root", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "visible.txt"), "Hello from the allowed root.\n", "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", {
        protocolVersion: "2025-06-18",
        capabilities: {},
        clientInfo: { name: "test", version: "1.0.0" }
      }),
      JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }),
      sendRequest(2, "tools/call", { name: "list_files", arguments: {} })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /visible\.txt/);
    assert.match(reply.result.content[0].text, /allowed root/);
  });
});

test("reads a text file inside the allowed root and rejects a parent-directory path", async () => {
  await withTempDirectory(async (root) => {
    const nestedDirectory = path.join(root, "notes");
    const outsidePath = path.join(path.dirname(root), `${path.basename(root)}-outside.txt`);
    await mkdir(nestedDirectory);
    await writeFile(path.join(nestedDirectory, "meeting.txt"), "Project status: green.\n", "utf8");
    await writeFile(outsidePath, "This text must never be exposed.\n", "utf8");

    try {
      const result = await runServer(root, [
        sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
        sendRequest(2, "tools/call", {
          name: "read_file",
          arguments: { path: "notes/meeting.txt" }
        }),
        sendRequest(3, "tools/call", {
          name: "read_file",
          arguments: { path: `../${path.basename(outsidePath)}` }
        })
      ]);

      assert.equal(result.exitCode, 0, result.stderr);
      const safeReply = result.replies.find((message) => message.id === 2);
      const rejectedReply = result.replies.find((message) => message.id === 3);
      assert.equal(safeReply.error, undefined);
      assert.equal(rejectedReply.error, undefined);
      assert.equal(safeReply.result.isError, false);
      assert.match(safeReply.result.content[0].text, /Project status: green/);
      assert.match(safeReply.result.content[0].text, /untrusted data/i);
      assert.equal(rejectedReply.result.isError, true);
      assert.match(rejectedReply.result.content[0].text, /outside the allowed root/i);
      assert.doesNotMatch(rejectedReply.result.content[0].text, /must never be exposed/);
    } finally {
      await rm(outsidePath, { force: true });
    }
  });
});

test("rejects a directory junction that resolves outside the allowed root", async (t) => {
  await withTempDirectory(async (root) => {
    const outsideDirectory = path.join(path.dirname(root), `${path.basename(root)}-outside`);
    const outsidePath = path.join(outsideDirectory, "secret.txt");
    const linkPath = path.join(root, "outside-link");
    await mkdir(outsideDirectory);
    await writeFile(outsidePath, "This text must never be exposed through a link.\n", "utf8");
    try {
      try {
        await symlink(outsideDirectory, linkPath, "junction");
      } catch (caught) {
        t.skip(`Creating a Windows directory junction is unavailable: ${caught.code ?? "unknown error"}`);
        return;
      }
      const result = await runServer(root, [
        sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
        sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "outside-link/secret.txt" } })
      ]);

      assert.equal(result.exitCode, 0, result.stderr);
      const reply = result.replies.find((message) => message.id === 2);
      assert.equal(reply.error, undefined);
      assert.equal(reply.result.isError, true);
      assert.match(reply.result.content[0].text, /outside the allowed root/i);
      assert.doesNotMatch(reply.result.content[0].text, /must never be exposed/);
    } finally {
      await rm(outsideDirectory, { recursive: true, force: true });
    }
  });
});

test("does not list, search, or read a dotenv secret file", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, ".env"), "API_TOKEN=must-not-leak\n", "utf8");
    await writeFile(path.join(root, "public.txt"), "Public project notes.\n", "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "list_files", arguments: {} }),
      sendRequest(3, "tools/call", { name: "read_file", arguments: { path: ".env" } }),
      sendRequest(4, "tools/call", { name: "search_files", arguments: { query: "must-not-leak" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const listReply = result.replies.find((message) => message.id === 2);
    const readReply = result.replies.find((message) => message.id === 3);
    const searchReply = result.replies.find((message) => message.id === 4);
    assert.equal(listReply.result.isError, false);
    assert.doesNotMatch(listReply.result.content[0].text, /\.env/);
    assert.equal(readReply.result.isError, true);
    assert.match(readReply.result.content[0].text, /sensitive/i);
    assert.doesNotMatch(readReply.result.content[0].text, /must-not-leak/);
    assert.equal(searchReply.result.isError, false);
    assert.doesNotMatch(searchReply.result.content[0].text, /must-not-leak/);
  });
});

test("extracts text from a modern Word document inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const document = createStoredZip([
      ["[Content_Types].xml", "<Types></Types>"],
      ["word/document.xml", "<w:document xmlns:w=\"urn:test\"><w:body><w:p><w:r><w:t>DOCX extraction works.</w:t></w:r></w:p></w:body></w:document>"]
    ]);
    await writeFile(path.join(root, "report.docx"), document);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "report.docx" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /DOCX extraction works/);
  });
});

test("extracts cell values from a modern Excel workbook inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const workbook = createStoredZip([
      ["[Content_Types].xml", "<Types></Types>"],
      ["xl/sharedStrings.xml", "<sst xmlns=\"urn:test\"><si><t>Name</t></si><si><t>Status</t></si><si><t>Ada</t></si><si><t>Ready</t></si></sst>"],
      ["xl/worksheets/sheet1.xml", "<worksheet xmlns=\"urn:test\"><sheetData><row r=\"1\"><c r=\"A1\" t=\"s\"><v>0</v></c><c r=\"B1\" t=\"s\"><v>1</v></c></row><row r=\"2\"><c r=\"A2\" t=\"s\"><v>2</v></c><c r=\"B2\" t=\"s\"><v>3</v></c></row></sheetData></worksheet>"]
    ]);
    await writeFile(path.join(root, "status.xlsx"), workbook);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "status.xlsx" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /Name/);
    assert.match(reply.result.content[0].text, /Ready/);
  });
});

test("extracts text from a modern PowerPoint presentation inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const presentation = createStoredZip([
      ["[Content_Types].xml", "<Types></Types>"],
      ["ppt/slides/slide1.xml", "<p:sld xmlns:p=\"urn:p\" xmlns:a=\"urn:a\"><a:t>Opening slide</a:t></p:sld>"],
      ["ppt/slides/slide2.xml", "<p:sld xmlns:p=\"urn:p\" xmlns:a=\"urn:a\"><a:t>Conclusion slide</a:t></p:sld>"]
    ]);
    await writeFile(path.join(root, "deck.pptx"), presentation);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "deck.pptx" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /Opening slide/);
    assert.match(reply.result.content[0].text, /Conclusion slide/);
  });
});

test("extracts embedded text from a compressed PDF inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "report.pdf"), createCompressedPdf("PDF extraction works."));
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "report.pdf" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /PDF extraction works/);
  });
});

test("searches recursively within the allowed root", async () => {
  await withTempDirectory(async (root) => {
    await mkdir(path.join(root, "notes"));
    await writeFile(path.join(root, "notes", "plan.md"), "The hummingbird migration is ready.\n", "utf8");
    await writeFile(path.join(root, "unrelated.txt"), "Nothing to see here.\n", "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", {
        name: "search_files",
        arguments: { query: "hummingbird" }
      })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /notes[\\/]plan\.md/);
    assert.match(reply.result.content[0].text, /hummingbird migration/i);
    assert.doesNotMatch(reply.result.content[0].text, /unrelated\.txt/);
  });
});

test("extracts readable text rather than markup from an HTML file", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(
      path.join(root, "article.html"),
      "<html><head><title>Example</title><style>.hidden { display:none }</style></head><body><h1>Research notes</h1><p>Useful &amp; safe text.</p><script>doNotExpose()</script></body></html>",
      "utf8"
    );
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "article.html" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /Research notes/);
    assert.match(reply.result.content[0].text, /Useful & safe text/);
    assert.doesNotMatch(reply.result.content[0].text, /<h1>|doNotExpose|display:none/);
  });
});

test("extracts text from an OpenDocument text file inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const document = createStoredZip([
      ["mimetype", "application/vnd.oasis.opendocument.text"],
      ["content.xml", "<office:document-content xmlns:office=\"urn:office\" xmlns:text=\"urn:text\"><office:body><text:p>OpenDocument extraction works.</text:p></office:body></office:document-content>"]
    ]);
    await writeFile(path.join(root, "notes.odt"), document);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "notes.odt" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /OpenDocument extraction works/);
  });
});

test("reports dimensions for a PNG image inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "diagram.png"), createPngHeader(640, 480));
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "diagram.png" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /PNG image/);
    assert.match(reply.result.content[0].text, /640 × 480/);
    assert.match(reply.result.content[0].text, /does not perform OCR/i);
  });
});

test("caps a large read and tells the caller how to request the next segment", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "large.txt"), `${"a".repeat(150_000)}END-OF-FILE`, "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "large.txt" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /truncated/i);
    assert.match(reply.result.content[0].text, /start_character/i);
    assert.doesNotMatch(reply.result.content[0].text, /END-OF-FILE/);
  });
});

test("continues a truncated read from an explicit character offset", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "large.txt"), `${"a".repeat(100_000)}NEXT-SEGMENT`, "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", {
        name: "read_file",
        arguments: { path: "large.txt", start_character: 100_000, max_characters: 100 }
      })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /NEXT-SEGMENT/);
    assert.doesNotMatch(reply.result.content[0].text, /Output truncated/);
  });
});

test("reads a UTF-16 text file inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const utf16 = Buffer.concat([Buffer.from([0xff, 0xfe]), Buffer.from("UTF-16 text works.", "utf16le")]);
    await writeFile(path.join(root, "windows-note.txt"), utf16);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "windows-note.txt" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /UTF-16 text works/);
  });
});

test("extracts readable text from an RTF document inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "note.rtf"), "{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Arial;}}\\f0\\fs24 Hello \\b bold\\b0\\par Second line}", "utf8");
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "note.rtf" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /Hello bold/);
    assert.match(reply.result.content[0].text, /Second line/);
    assert.doesNotMatch(reply.result.content[0].text, /\\rtf1|\\b0/);
  });
});

test("reports dimensions for a JPEG image inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    await writeFile(path.join(root, "photo.jpg"), createJpegHeader(200, 100));
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "photo.jpg" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /JPEG image/);
    assert.match(reply.result.content[0].text, /200 × 100/);
  });
});

test("extracts chapters from an EPUB file inside the allowed root", async () => {
  await withTempDirectory(async (root) => {
    const book = createStoredZip([
      ["mimetype", "application/epub+zip"],
      ["OEBPS/chapter1.xhtml", "<html><body><h1>Chapter One</h1><p>EPUB extraction works.</p></body></html>"],
      ["OEBPS/chapter2.xhtml", "<html><body><h1>Chapter Two</h1><p>More readable text.</p></body></html>"]
    ]);
    await writeFile(path.join(root, "book.epub"), book);
    const result = await runServer(root, [
      sendRequest(1, "initialize", { protocolVersion: "2025-06-18" }),
      sendRequest(2, "tools/call", { name: "read_file", arguments: { path: "book.epub" } })
    ]);

    assert.equal(result.exitCode, 0, result.stderr);
    const reply = result.replies.find((message) => message.id === 2);
    assert.equal(reply.error, undefined);
    assert.equal(reply.result.isError, false);
    assert.match(reply.result.content[0].text, /Chapter One/);
    assert.match(reply.result.content[0].text, /More readable text/);
  });
});
