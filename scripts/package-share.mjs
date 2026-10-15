import { readFile, writeFile, mkdir, realpath, lstat } from "node:fs/promises";
import { createHash } from "node:crypto";
import { deflateRawSync } from "node:zlib";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Deliberate allowlist: adding a file anywhere else never makes it shareable.
export const SHARE_FILES = [
  ".gitignore", "package.json", "README.md", "README.en.md", "CHANGELOG.md", "CONTRIBUTING.md",
  "src/index.mjs", "test/mcp-server.test.mjs", "test/sharing.test.mjs", "test/distribution.test.mjs",
  "scripts/package-share.mjs", "scripts/smoke.mjs", "scripts/tunnel.mjs", "scripts/tunnel.ps1",
  "examples/stdio-client.json", "examples/files/hello-local.md", "examples/files/notes/meeting.txt",
  "docs/QUICKSTART.md", "docs/CHATGPT.md", "docs/USER-GUIDE.md", "docs/FORMATS.md",
  "docs/SECURITY.md", "docs/TROUBLESHOOTING.md", "docs/COMPARISON.md", "docs/SHARING.md"
];

export function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

function zip(entries) {
  const locals = [], central = [];
  let offset = 0;
  for (const [name, contents] of entries) {
    const nameBytes = Buffer.from(name, "utf8");
    const compressed = deflateRawSync(contents);
    const crc = crc32(contents);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50);
    local.writeUInt16LE(20, 4);
    local.writeUInt16LE(0x800, 6); // UTF-8 filenames
    local.writeUInt16LE(8, 8);
    local.writeUInt16LE(33, 12); // deterministic 1980-01-01
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(compressed.length, 18);
    local.writeUInt32LE(contents.length, 22);
    local.writeUInt16LE(nameBytes.length, 26);
    const directory = Buffer.alloc(46);
    directory.writeUInt32LE(0x02014b50);
    directory.writeUInt16LE(20, 4);
    directory.writeUInt16LE(20, 6);
    directory.writeUInt16LE(0x800, 8);
    directory.writeUInt16LE(8, 10);
    directory.writeUInt16LE(33, 14);
    directory.writeUInt32LE(crc, 16);
    directory.writeUInt32LE(compressed.length, 20);
    directory.writeUInt32LE(contents.length, 24);
    directory.writeUInt16LE(nameBytes.length, 28);
    directory.writeUInt32LE(offset, 42);
    locals.push(local, nameBytes, compressed);
    central.push(directory, nameBytes);
    offset += local.length + nameBytes.length + compressed.length;
  }
  const centralBytes = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50);
  end.writeUInt16LE(entries.length, 8);
  end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(centralBytes.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, centralBytes, end]);
}

export async function createShareArchive(projectRoot, outputDirectory = path.join(projectRoot, "dist")) {
  const root = await realpath(projectRoot);
  const entries = [], manifestFiles = [];
  let totalBytes = 0;
  for (const name of [...SHARE_FILES].sort()) {
    let current = root;
    for (const segment of name.split("/")) {
      current = path.join(current, segment);
      if ((await lstat(current)).isSymbolicLink()) throw new Error(`Refusing linked share file: ${name}`);
    }
    const info = await lstat(current);
    if (!info.isFile() || info.size > 2 * 1024 * 1024) throw new Error(`Unexpected share file type or size: ${name}`);
    const bytes = await readFile(current);
    totalBytes += bytes.length;
    if (totalBytes > 20 * 1024 * 1024) throw new Error("Share source exceeds the 20 MiB safety limit.");
    const text = bytes.toString("utf8");
    if (/\bsk-[A-Za-z0-9_-]{20,}|\btunnel_[a-f0-9]{32}\b/i.test(text)) throw new Error(`Possible credential or personal tunnel ID in ${name}; packaging stopped. No value was logged.`);
    entries.push([name, bytes]);
    manifestFiles.push({ path: name, bytes: bytes.length, sha256: sha256(bytes) });
  }
  const pkg = JSON.parse(entries.find(([name]) => name === "package.json")[1].toString("utf8"));
  if (!/^\d+\.\d+\.\d+$/.test(pkg.version)) throw new Error("Invalid release version.");
  const prefix = `local-readonly-files-mcp-${pkg.version}`;
  const manifest = Buffer.from(JSON.stringify({ version: pkg.version, files: manifestFiles }, null, 2) + "\n");
  const archive = zip([...entries, ["SHARE-MANIFEST.json", manifest]].map(([name, bytes]) => [`${prefix}/${name}`, bytes]));
  await mkdir(outputDirectory, { recursive: true });
  const output = path.join(outputDirectory, `${prefix}.zip`);
  const digest = sha256(archive);
  await writeFile(output, archive);
  await writeFile(`${output}.sha256`, `${digest}  ${path.basename(output)}\n`);
  return { output, sha256: digest, files: entries.length + 1, bytes: archive.length };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  createShareArchive(fileURLToPath(new URL("..", import.meta.url)))
    .then(result => process.stdout.write(`${JSON.stringify(result, null, 2)}\n`))
    .catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
