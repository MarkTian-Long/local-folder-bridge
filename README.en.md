# LocalFolderBridge

[中文](README.md) | [English](README.en.md)

Connect AI to explicitly authorized local material through MCP. This repository retains two independent implementations, both read-only by default. Neither provides a remote shell.

This is the English repository overview. Linked detailed guides and the Python graphical interface may still be in Chinese.

| Implementation | Intended users | Start here |
| --- | --- | --- |
| Python graphical edition 1.1.1 | Windows users who want a Chinese interface, multiple authorized directories, and local approval for each operation | [Installation and manual](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/LocalFolderBridge/README.md) |
| Node read-only edition 0.2.0 | Developers who want no third-party dependencies, one fixed directory, and stdio | The quick start below |

[Project overview](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/PROJECT.md) · [GitHub validation status](https://github.com/MarkTian-Long/local-folder-bridge/actions) · [Daily push and sync](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-SYNC.md) · [Publication process](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-PLAN.md)

The source is public. Pushes trigger documentation consistency checks and Windows/Linux regression checks. Local changes still require an explicit commit and push; files are not uploaded in the background, and running services do not update automatically. Formal Release downloads and automatic startup at login are not enabled.

Licenses remain separate: the Python subdirectory contains an MIT LICENSE. The Node `package.json` remains `private: true` / `UNLICENSED` and is not automatically published to npm. The repository has not relicensed both implementations under MIT.

## Node read-only edition

Let an MCP-compatible AI client read one local folder you explicitly authorize: browse directories, read text, and search contents. You can connect it to ChatGPT on the web through your own OpenAI Secure MCP Tunnel.

**Read this first: this is a lightweight text extraction tool, not a full Office/PDF reader. Images return dimensions only, and scanned documents do not receive OCR. Read-only does not mean no data leaves your machine: when invoked, returned file excerpts are sent to the AI service you connect.**

Version: 0.2.0 · Built with Node.js core modules · No third-party runtime dependencies · MCP stdio transport.

The rest of this page and the compact Node ZIP describe only the read-only edition. The Python graphical edition has its own manual and package and does not automatically replace an existing service. The GitHub navigation above requires network access; relative documentation links inside the Node ZIP work offline.

## Five-minute local trial

1. Install a currently supported LTS release from [Node.js](https://nodejs.org/). The code requires Node.js ≥ 20.
2. Clone the repository or extract the compact Node share package, then open a terminal in the folder containing `package.json`.
3. Run these two commands. No `npm install`, API key, or login is needed:

```powershell
node --version
node scripts/smoke.mjs
```

`PASS` confirms local initialization, tool discovery, directory listing, reading, searching, and out-of-scope refusal. **It does not mean ChatGPT is connected.**

Next: [Beginner setup](docs/QUICKSTART.md) → [ChatGPT connection](docs/CHATGPT.md) → [Prompts and user guide](docs/USER-GUIDE.md).

## Three tools

| Tool | Purpose | Key parameters |
| --- | --- | --- |
| `list_files` | Browse the authorized directory and its subdirectories | `path`, `offset`, `limit` |
| `read_file` | Read text or extract document text | `path`, `start_character`, `max_characters` |
| `search_files` | Search file contents for a literal phrase, not file names | `query`, `path`, `offset`, `limit` |

All tools declare read-only, non-destructive behavior and no open internet access. Names and contents are treated as untrusted data. Tools cannot write, delete, run commands, or read arbitrary URLs.

## Two connection options

- Local MCP client: configure the client to launch `node src/index.mjs --root <authorized-folder>`. See the [stdio configuration example](examples/stdio-client.json). Configuration formats vary by client.
- ChatGPT on the web: run the official `tunnel-client` separately and connect your own Tunnel. See the [connection guide](docs/CHATGPT.md). Do not send others your keys or connection configuration.

The installation directory and authorized directory can differ. Use a dedicated folder containing only the material you intend to share; do not authorize an entire drive or your home directory. Renaming the project directory requires updating existing Tunnel startup commands. Read [troubleshooting](docs/TROUBLESHOOTING.md) first.

## Documentation

- [Beginner installation and local acceptance](docs/QUICKSTART.md)
- [ChatGPT on the web: configure, start, stop, and restart](docs/CHATGPT.md)
- [User guide, verification prompts, and tool parameters](docs/USER-GUIDE.md)
- [Supported formats and actual limits](docs/FORMATS.md)
- [Security, privacy, and known risks](docs/SECURITY.md)
- [FAQ and troubleshooting](docs/TROUBLESHOOTING.md)
- [Related GitHub projects and improvement roadmap](docs/COMPARISON.md)
- [How to share safely](docs/SHARING.md)
- [Development and tests](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## Validation and packaging

```powershell
node --test
node scripts/smoke.mjs
node scripts/package-share.mjs
```

The final command creates `dist/local-readonly-files-mcp-0.2.0.zip` and a SHA-256 checksum file. Packaging uses an explicit file allowlist. It excludes `.tunnel-client`, the old `tools` directory, runtime logs, executables, and arbitrary new files. Security scanning is not comprehensive; inspect the share package before sending it.

The Node implementation has not selected an open-source license. It remains `private: true` / `UNLICENSED` and is not automatically published to npm. `private` is an npm publication setting, not a statement that the GitHub repository is private. See the [sharing guide](docs/SHARING.md) for authorization details.
