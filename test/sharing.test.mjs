import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { spawn } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const server = fileURLToPath(new URL("../src/index.mjs", import.meta.url));
async function fixture(run) {
  const root = await mkdtemp(path.join(os.tmpdir(), "readonly-mcp-sharing-"));
  try { await run(root); } finally { await rm(root, { recursive: true, force: true }); }
}
async function rpc(root, messages, cliArgs = ["--root", root]) {
  const child = spawn(process.execPath, [server, ...cliArgs], { windowsHide: true });
  let stdout = "", stderr = "";
  child.stdout.on("data", b => { stdout += b; });
  child.stderr.on("data", b => { stderr += b; });
  child.stdin.on("error", () => {});
  child.stdin.end(messages.map(m => typeof m === "string" ? m : JSON.stringify(m)).join("\n") + "\n");
  const code = await new Promise((resolve, reject) => { child.on("error", reject); child.on("close", resolve); });
  return { code, stdout, stderr, replies: cliArgs.includes("--root") ? stdout.trim().split(/\r?\n/).filter(Boolean).map(JSON.parse) : [] };
}
const request = (id, method, params = {}) => ({ jsonrpc: "2.0", id, method, params });
const call = (id, name, args = {}) => request(id, "tools/call", { name, arguments: args });

test("all tools declare read-only, closed-world annotations and output schemas", async () => {
  await fixture(async root => {
    const { replies } = await rpc(root, [request(1, "tools/list")]);
    for (const tool of replies[0].result.tools) {
      assert.deepEqual(tool.annotations, { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false });
      assert.equal(tool.outputSchema.type, "object");
    }
  });
});

test("list_files browses subfolders with stable pagination without exposing the absolute root", async () => {
  await fixture(async root => {
    await mkdir(path.join(root, "notes"));
    for (const name of ["a.md", "b.md", "c.md"]) await writeFile(path.join(root, "notes", name), name);
    const { replies } = await rpc(root, [call(1, "list_files", { path: "notes", limit: 2 }), call(2, "list_files", { path: "notes", limit: 2, offset: 2 })]);
    const first = replies[0].result.structuredContent;
    assert.deepEqual(first.entries.map(e => e.path), ["notes/a.md", "notes/b.md"]);
    assert.equal(first.next_offset, 2);
    assert.equal(replies[1].result.structuredContent.next_offset, null);
    assert.equal(JSON.stringify(replies).includes(root), false);
  });
});

test("tunnel and agent configuration is excluded from listing, reads and searches", async () => {
  await fixture(async root => {
    for (const dir of [".tunnel-client", ".codex", ".agents", "node_modules"]) {
      await mkdir(path.join(root, dir));
      await writeFile(path.join(root, dir, "private.txt"), "private-marker");
    }
    const { replies } = await rpc(root, [call(1, "list_files"), call(2, "read_file", { path: ".tunnel-client/private.txt" }), call(3, "search_files", { query: "private-marker" })]);
    assert.doesNotMatch(replies[0].result.content[0].text, /\.tunnel-client|\.codex|\.agents|node_modules/);
    assert.equal(replies[1].result.isError, true);
    assert.deepEqual(replies[2].result.structuredContent.matches, []);
  });
});

test("protected lexical paths cannot be bypassed through an in-root junction", async () => {
  await fixture(async root => {
    await mkdir(path.join(root, "safe"));
    await writeFile(path.join(root, "safe", "note.txt"), "must-not-leak");
    await symlink(path.join(root, "safe"), path.join(root, ".tunnel-client"), "junction");
    const { replies } = await rpc(root, [call(1, "read_file", { path: ".tunnel-client/note.txt" })]);
    assert.equal(replies[0].result.isError, true);
    assert.doesNotMatch(replies[0].result.content[0].text, /must-not-leak/);
  });
});

test("read results include continuation metadata and preserve extracted text separately", async () => {
  await fixture(async root => {
    await writeFile(path.join(root, "note.txt"), "abcdef");
    const { replies } = await rpc(root, [call(1, "read_file", { path: "note.txt", max_characters: 3 }), call(2, "read_file", { path: "note.txt", start_character: 3 })]);
    assert.equal(replies[0].result.structuredContent.text, "abc");
    assert.equal(replies[0].result.structuredContent.next_start_character, 3);
    assert.equal(replies[1].result.structuredContent.text, "def");
    assert.equal(replies[1].result.structuredContent.next_start_character, null);
  });
});

test("search is content-based, scoped and paginated with skipped-file reporting", async () => {
  await fixture(async root => {
    await mkdir(path.join(root, "notes"));
    for (const name of ["a.txt", "b.txt", "c.txt"]) await writeFile(path.join(root, "notes", name), "Project NEEDLE verified");
    await writeFile(path.join(root, "notes", "broken.docx"), "not-a-zip");
    await writeFile(path.join(root, "outside-scope.txt"), "needle");
    const { replies } = await rpc(root, [call(1, "search_files", { query: "needle", path: "notes", limit: 2 }), call(2, "search_files", { query: "needle", path: "notes", limit: 2, offset: 2 })]);
    const first = replies[0].result.structuredContent;
    assert.equal(first.matches.length, 2);
    assert.equal(first.next_offset, 2);
    assert.equal(first.skipped_files, 1);
    assert.equal(first.scan_truncated, false);
    assert.deepEqual(replies[1].result.structuredContent.matches.map(m => m.path), ["notes/c.txt"]);
  });
});

test("depth-limited search reports that results are incomplete", async () => {
  await fixture(async root => {
    const nested = path.join(root, ...Array.from({ length: 25 }, () => "d"));
    await mkdir(nested, { recursive: true });
    await writeFile(path.join(nested, "note.txt"), "deep-marker");
    const { replies } = await rpc(root, [call(1, "search_files", { query: "deep-marker" })]);
    assert.equal(replies[0].result.structuredContent.scan_truncated, true);
  });
});

test("invalid JSON-RPC messages do not crash the server; ping and unknown methods have standard replies", async () => {
  await fixture(async root => {
    const { code, replies } = await rpc(root, ["{broken", "null", "[]", request(1, "ping"), request(2, "missing"), { jsonrpc: "2.0", method: "notifications/initialized" }]);
    assert.equal(code, 0);
    assert.deepEqual(replies.map(r => r.error?.code ?? "ok"), [-32700, -32600, -32600, "ok", -32601]);
    assert.deepEqual(replies[3].result, {});
  });
});

test("rejects unknown arguments and invalid pagination rather than ignoring them", async () => {
  await fixture(async root => {
    const { replies } = await rpc(root, [call(1, "list_files", { offset: -1 }), call(2, "list_files", { accidental: true }), call(3, "search_files", { query: "", limit: 200 }), call(4, "missing_tool")]);
    for (const reply of replies) assert.equal(reply.error?.code, -32602);
  });
});

test("null arguments are invalid instead of silently granting default directory listing", async () => {
  await fixture(async root => {
    const { replies } = await rpc(root, [call(1, "list_files", null)]);
    assert.equal(replies[0].error?.code, -32602);
  });
});

test("negotiates an actually supported protocol version", async () => {
  await fixture(async root => {
    const { replies } = await rpc(root, [request(1, "initialize", { protocolVersion: "unknown-future-version" })]);
    assert.equal(replies[0].result.protocolVersion, "2025-06-18");
  });
});

test("all successful structured results satisfy their declared output schema", async () => {
  function validate(value, schema) {
    if (schema.enum) assert.ok(schema.enum.includes(value));
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (schema.type) assert.ok(types.some(type => type === "null" ? value === null : type === "integer" ? Number.isInteger(value) : type === "array" ? Array.isArray(value) : type === "object" ? value !== null && typeof value === "object" && !Array.isArray(value) : typeof value === type));
    if (value === null) return;
    if (schema.type === "object") {
      for (const key of schema.required ?? []) assert.ok(Object.hasOwn(value, key), key);
      for (const [key, item] of Object.entries(value)) { assert.ok(Object.hasOwn(schema.properties, key), key); validate(item, schema.properties[key]); }
    }
    if (schema.type === "array") for (const item of value) validate(item, schema.items);
    if (typeof value === "number" && schema.minimum !== undefined) assert.ok(value >= schema.minimum);
  }
  await fixture(async root => {
    await writeFile(path.join(root, "sample.txt"), "schema-check");
    const { replies } = await rpc(root, [request(1, "tools/list"), call(2, "list_files"), call(3, "read_file", { path: "sample.txt", max_characters: 4 }), call(4, "search_files", { query: "schema" })]);
    for (const [index, name] of ["list_files", "read_file", "search_files"].entries()) {
      validate(replies[index + 1].result.structuredContent, replies[0].result.tools.find(tool => tool.name === name).outputSchema);
    }
  });
});

test("missing files produce actionable errors without leaking server paths", async () => {
  await fixture(async root => {
    const { replies } = await rpc(root, [call(1, "read_file", { path: "missing.txt" })]);
    assert.equal(replies[0].result.isError, true);
    assert.match(replies[0].result.content[0].text, /not found/i);
    assert.equal(replies[0].result.content[0].text.includes(root), false);
  });
});

test("CLI help and version work without granting a root; files cannot be used as roots", async () => {
  await fixture(async root => {
    const help = await rpc(root, [], ["--help"]);
    assert.equal(help.code, 0);
    assert.match(help.stdout, /--root/);
    const version = await rpc(root, [], ["--version"]);
    assert.match(version.stdout, /0\.2\.0/);
    await writeFile(path.join(root, "note.txt"), "hello");
    const invalid = await rpc(root, [], ["--root", path.join(root, "note.txt")]);
    assert.notEqual(invalid.code, 0);
    assert.match(invalid.stderr, /directory/i);
  });
});
