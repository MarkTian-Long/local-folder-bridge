import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile, rm, copyFile, symlink, access } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import test from "node:test";
import { randomBytes, createHash } from "node:crypto";
import { inflateRawSync } from "node:zlib";
import { fileURLToPath } from "node:url";
import { parseOptions, buildClientArgs } from "../scripts/tunnel.mjs";
import { createShareArchive, SHARE_FILES, crc32 } from "../scripts/package-share.mjs";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
async function fixture(run) {
  const root = await mkdtemp(path.join(os.tmpdir(), "mcp-distribution-"));
  try {
    for (const file of SHARE_FILES) {
      await mkdir(path.dirname(path.join(root, file)), { recursive: true });
      await copyFile(path.join(projectRoot, file), path.join(root, file));
    }
    await run(root);
  } finally { await rm(root, { recursive: true, force: true }); }
}

function readZip(bytes) {
  const entries = new Map();
  let offset = 0;
  while (bytes.readUInt32LE(offset) === 0x04034b50) {
    const length = bytes.readUInt32LE(offset + 18);
    const nameLength = bytes.readUInt16LE(offset + 26);
    const extraLength = bytes.readUInt16LE(offset + 28);
    const name = bytes.subarray(offset + 30, offset + 30 + nameLength).toString("utf8");
    const start = offset + 30 + nameLength + extraLength;
    const contents = inflateRawSync(bytes.subarray(start, start + length));
    assert.equal(crc32(contents), bytes.readUInt32LE(offset + 14));
    entries.set(name, contents);
    offset = start + length;
  }
  assert.equal(bytes.readUInt32LE(offset), 0x02014b50);
  return entries;
}

test("CRC32 uses the standard ZIP checksum", () => {
  assert.equal(crc32(Buffer.from("123456789")), 0xcbf43926);
});

test("share archive excludes unlisted files, is reproducible and has verifiable per-file hashes", async () => {
  await fixture(async root => {
    const privateMarker = randomBytes(24).toString("hex");
    for (const file of [".env", ".tunnel-client/local.yaml", "tools/private.js", "docs/private-note.md"]) {
      await mkdir(path.dirname(path.join(root, file)), { recursive: true });
      await writeFile(path.join(root, file), privateMarker);
    }
    const first = await createShareArchive(root);
    const bytes = await readFile(first.output);
    const entries = readZip(bytes);
    for (const [name, contents] of entries) {
      assert.doesNotMatch(name, /\.tunnel-client|private-note|tools\/private|\/\.env$/);
      assert.equal(contents.toString("utf8").includes(privateMarker), false);
    }
    const manifestName = [...entries.keys()].find(name => name.endsWith("/SHARE-MANIFEST.json"));
    const prefix = manifestName.slice(0, -"SHARE-MANIFEST.json".length);
    const manifest = JSON.parse(entries.get(manifestName));
    for (const entry of manifest.files) {
      assert.equal(createHash("sha256").update(entries.get(prefix + entry.path)).digest("hex"), entry.sha256);
    }
    const second = await createShareArchive(root);
    assert.equal(second.sha256, first.sha256);
  });
});

test("packager refuses credential-shaped data in a shareable file without echoing it", async () => {
  await fixture(async root => {
    const secret = "sk-" + randomBytes(32).toString("hex");
    await writeFile(path.join(root, "README.md"), secret);
    await assert.rejects(createShareArchive(root), error => /Possible credential/.test(error.message) && !error.message.includes(secret));
  });
});

test("packager rejects a junction replacing a shareable directory", async () => {
  await fixture(async root => {
    const docs = path.join(root, "docs");
    // Only removes the fresh test-owned copy, never the user's project.
    await rm(docs, { recursive: true, force: true });
    await symlink(path.join(projectRoot, "docs"), docs, "junction");
    await assert.rejects(createShareArchive(root), /Refusing linked/);
  });
});

test("tunnel init quotes spaces, uses portable slashes and never embeds a runtime key", () => {
  const options = parseOptions(["init", "--client", "example.exe", "--tunnel", "tunnel_" + "0".repeat(32)]);
  const args = buildClientArgs(options, "C:\\Program Files\\nodejs\\node.exe", "D:\\MCP Demo\\src\\index.mjs", "D:\\Shared Notes");
  const command = args[args.indexOf("--mcp-command") + 1];
  assert.equal(command, '"C:/Program Files/nodejs/node.exe" "D:/MCP Demo/src/index.mjs" "--root" "D:/Shared Notes"');
  assert.ok(args.includes("env:CONTROL_PLANE_API_KEY"));
  assert.equal(args.includes("--force"), false);
  assert.ok(args.includes("127.0.0.1:0"));
});

test("tunnel launcher rejects ambiguous or unsafe options", () => {
  assert.throws(() => parseOptions(["run", "--client", "example.exe", "--profile", "../../private"]), /Invalid profile/);
  assert.throws(() => parseOptions(["run", "--client", "example.exe", "--root", "."]), /init-only/);
  assert.throws(() => parseOptions(["run", "--client", "example.exe", "--api-key", "placeholder"]), /Invalid/);
  assert.throws(() => parseOptions(["run", "--client", "a", "--client", "b"]), /duplicate/);
});

test("all relative handbook links exist in the share allowlist", async () => {
  for (const file of SHARE_FILES.filter(name => name.endsWith(".md"))) {
    const text = await readFile(path.join(projectRoot, file), "utf8");
    for (const match of text.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
      const target = match[1].split("#")[0];
      if (!target || /^[a-z]+:/i.test(target)) continue;
      const absolute = path.resolve(projectRoot, path.dirname(file), decodeURIComponent(target));
      await access(absolute);
      assert.ok(SHARE_FILES.includes(path.relative(projectRoot, absolute).split(path.sep).join("/")), `${file}: ${target} is not shared`);
    }
  }
});
