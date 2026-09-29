import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const server = fileURLToPath(new URL("../src/index.mjs", import.meta.url));
const root = fileURLToPath(new URL("../examples/files", import.meta.url));
const messages = [
  { id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "local-smoke", version: "1.0.0" } } },
  { id: 2, method: "tools/list" },
  { id: 3, method: "tools/call", params: { name: "list_files", arguments: {} } },
  { id: 4, method: "tools/call", params: { name: "read_file", arguments: { path: "hello-local.md" } } },
  { id: 5, method: "tools/call", params: { name: "search_files", arguments: { query: "本地桥接验证", path: "notes" } } },
  { id: 6, method: "tools/call", params: { name: "read_file", arguments: { path: "../stdio-client.json" } } }
];
const child = spawn(process.execPath, [server, "--root", root], { windowsHide: true });
let stdout = "", stderr = "";
const timeout = setTimeout(() => child.kill(), 15_000);
try {
  child.stdout.on("data", chunk => { stdout += chunk; });
  child.stderr.on("data", chunk => { stderr += chunk; });
  child.stdin.on("error", () => {});
  child.stdin.end(messages.map(message => JSON.stringify({ jsonrpc: "2.0", ...message })).join("\n") + "\n");
  const code = await new Promise((resolve, reject) => { child.once("error", reject); child.once("close", resolve); });
  assert.equal(code, 0, stderr || "Server failed or timed out.");
  const replies = stdout.trim().split(/\r?\n/).map(JSON.parse);
  assert.equal(replies.length, 6);
  assert.equal(replies[1].result.tools.length, 3);
  assert.ok(replies[2].result.structuredContent.entries.some(entry => entry.path === "hello-local.md"));
  assert.match(replies[3].result.structuredContent.text, /薄荷书架/);
  assert.equal(replies[4].result.structuredContent.matches[0].path, "notes/meeting.txt");
  assert.equal(replies[5].result.isError, true);
  process.stdout.write("PASS: initialize, tools/list, list, read, search and root boundary. Local only; no ChatGPT/tunnel connection was tested.\n");
} catch (error) {
  process.stderr.write(`FAIL: ${error.message}\n`);
  process.exitCode = 1;
} finally { clearTimeout(timeout); }
