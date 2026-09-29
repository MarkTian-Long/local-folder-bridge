import { spawn } from "node:child_process";
import { realpath, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const projectRoot = fileURLToPath(new URL("..", import.meta.url));
const HELP = "Usage: node scripts/tunnel.mjs <init|doctor|run> --client <tunnel-client-path> [--profile <name>] [--profile-dir <directory>]\ninit also requires --tunnel <tunnel_id>; --root defaults to examples/files.\nFor doctor/run, provide CONTROL_PLANE_API_KEY through a secure prompt or secret manager, never as an argument.\n";

export function parseOptions(argv) {
  const [action, ...rest] = argv;
  if (!["init", "doctor", "run"].includes(action) || rest.length % 2) throw new Error(HELP);
  const options = { action, profile: "share-local-files", "profile-dir": path.join(projectRoot, ".tunnel-client"), root: path.join(projectRoot, "examples", "files") };
  const seen = new Set();
  for (let i = 0; i < rest.length; i += 2) {
    const name = rest[i].replace(/^--/, "");
    if (!rest[i].startsWith("--") || !["client", "profile", "profile-dir", "root", "tunnel"].includes(name) || seen.has(name) || !rest[i + 1]) throw new Error("Invalid or duplicate option.\n" + HELP);
    seen.add(name);
    options[name] = rest[i + 1];
  }
  if (!options.client) throw new Error("--client is required; download the official tunnel-client separately.");
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(options.profile)) throw new Error("Invalid profile name.");
  if (action === "init" && !/^tunnel_[a-f0-9]{32}$/i.test(options.tunnel ?? "")) throw new Error("init requires a valid --tunnel ID from your own account.");
  if (action !== "init" && (seen.has("root") || seen.has("tunnel"))) throw new Error("--root and --tunnel are init-only; run uses the saved profile. Create a new profile to change them.");
  return options;
}

export function buildClientArgs(options, nodePath, serverPath, allowedRoot) {
  const args = [options.action, "--profile", options.profile, "--profile-dir", path.resolve(options["profile-dir"])];
  if (options.action === "init") {
    const command = [nodePath, serverPath, "--root", allowedRoot].map(value => {
      if (/["\r\n]/.test(value)) throw new Error("Paths with quotes or newlines are not supported by the tunnel launcher.");
      return JSON.stringify(value.replaceAll("\\", "/"));
    }).join(" ");
    args.push("--sample", "sample_mcp_stdio_local", "--tunnel-id", options.tunnel, "--mcp-command", command,
      "--control-plane-api-key-ref", "env:CONTROL_PLANE_API_KEY", "--health-listen-addr", "127.0.0.1:0");
  }
  return args;
}

async function main() {
  if (process.argv.slice(2).join(" ") === "--help") { process.stdout.write(HELP); return; }
  const options = parseOptions(process.argv.slice(2));
  const client = await realpath(path.resolve(options.client));
  if (!(await stat(client)).isFile()) throw new Error("--client must point to the downloaded tunnel-client executable.");
  let allowedRoot;
  if (options.action === "init") {
    allowedRoot = await realpath(path.resolve(options.root));
    if (!(await stat(allowedRoot)).isDirectory()) throw new Error("--root must be a directory.");
    process.stdout.write(`Authorize read-only directory: ${allowedRoot}\nThis creates a local profile, not a tunnel in your account. Existing profiles are not overwritten.\n`);
  } else if (!process.env.CONTROL_PLANE_API_KEY?.trim()) {
    throw new Error("No runtime key. Use scripts/tunnel.ps1 for a hidden interactive prompt, or a secret manager environment variable.");
  }
  const args = buildClientArgs(options, process.execPath, path.join(projectRoot, "src", "index.mjs"), allowedRoot);
  const environment = { ...process.env };
  if (options.action === "init") delete environment.CONTROL_PLANE_API_KEY;
  const child = spawn(client, args, { env: environment, stdio: "inherit", windowsHide: true, shell: false });
  const exitCode = await new Promise((resolve, reject) => { child.once("error", reject); child.once("close", code => resolve(code ?? 1)); });
  process.exitCode = exitCode;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}
