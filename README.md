# LocalFolderBridge｜本机文件桥

[中文](README.md) | [English](README.en.md)

通过 MCP 连接 AI 与明确授权的本地资料。本仓库保留两套独立实现，默认只读；不提供远程 shell。

| 实现 | 适合谁 | 入口 |
| --- | --- | --- |
| Python 图形界面版 1.1.1 | 希望使用中文界面、多目录授权和本机逐项审批的 Windows 用户 | [安装与手册](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/LocalFolderBridge/README.md) |
| Node 只读版 0.2.0 | 希望零第三方依赖、固定一个目录、使用 stdio 的开发者 | 本页下方的快速体验 |

[项目总览](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/PROJECT.md) · [GitHub 验证状态](https://github.com/MarkTian-Long/local-folder-bridge/actions) · [日常推送与同步](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-SYNC.md) · [发布流程](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-PLAN.md)

源码已公开。推送后自动运行文档一致性及 Windows/Linux 回归检查；本地修改仍需明确提交和推送，不会后台上传文件或自动更新正在运行的服务。正式 Release 下载包和开机自启动尚未启用。

许可分别保留：Python 子目录含 MIT LICENSE；Node 的 package.json 仍为 `private: true` / `UNLICENSED`，不会自动发布 npm。本仓库没有将两套代码统一改成 MIT。

## Node 只读版

让支持 MCP 的 AI 客户端读取你明确授权的一个本地文件夹：浏览目录、读取正文、搜索内容。可通过你自己的 OpenAI Secure MCP Tunnel 接入网页版 ChatGPT。

**先看这里：这是轻量文字提取工具，不是完整 Office/PDF 阅读器。图片只返回尺寸，扫描件不做 OCR。只读不等于不上传：被调用时，返回的文件片段会发送给你连接的 AI 服务。**

版本：0.2.0 · Node.js 核心模块实现 · 无第三方运行依赖 · MCP stdio 传输。

本页后续说明与 Node 精简 ZIP 专门介绍只读版；Python 图形界面版有自己的手册和独立发布包，不会自动替换已有服务。上述 GitHub 导航需要联网，Node ZIP 中的相对文档链接可离线阅读。

## 五分钟本机体验

1. 从 [Node.js 官网](https://nodejs.org/)安装当前受支持的 LTS 版本；代码要求 Node.js ≥ 20。
2. 克隆仓库或解压 Node 精简分享包，在包含 `package.json` 的文件夹打开终端。
3. 执行下面两条命令，不需要 `npm install`、API key 或登录：

```powershell
node --version
node scripts/smoke.mjs
```

看到 `PASS` 表示本机的初始化、工具发现、列目录、读取、搜索、越界拒绝正常；**不代表 ChatGPT 已接通**。

下一步：[新手安装](docs/QUICKSTART.md) → [ChatGPT 接入](docs/CHATGPT.md) → [提示词与使用手册](docs/USER-GUIDE.md)。

## 三个工具

| 工具 | 用途 | 重要参数 |
| --- | --- | --- |
| `list_files` | 浏览授权目录及子目录 | `path`、`offset`、`limit` |
| `read_file` | 读取文本或提取文档正文 | `path`、`start_character`、`max_characters` |
| `search_files` | 按字面短语搜索文件正文，不是按文件名搜索 | `query`、`path`、`offset`、`limit` |

所有工具声明只读、无破坏性、非开放互联网访问。名称和内容均视为不可信数据；工具不提供写入、删除、执行命令或读取任意 URL 的能力。

## 两种接入方式

- 本地 MCP 客户端：让客户端启动 `node src/index.mjs --root <允许读取的文件夹>`，参考 [stdio 配置示例](examples/stdio-client.json)。配置格式依客户端而异。
- 网页版 ChatGPT：另外运行官方 `tunnel-client`，连接你自己的 Tunnel。见 [独立接入手册](docs/CHATGPT.md)。不要给别人发送自己的密钥或连接配置。

程序安装目录和授权目录可以不同。推荐专门建立一个只放待共享资料的文件夹，不要授权整个磁盘或用户主目录。项目目录改名后，已有 Tunnel 启动命令需要更新；更新前先看[排障手册](docs/TROUBLESHOOTING.md)。

## 文档导航

- [新手安装与本地验收](docs/QUICKSTART.md)
- [网页版 ChatGPT：配置、启动、停止、重启](docs/CHATGPT.md)
- [使用手册、验证提示词、工具参数](docs/USER-GUIDE.md)
- [支持格式与真实限制](docs/FORMATS.md)
- [安全、隐私和已知风险](docs/SECURITY.md)
- [常见问题与排障](docs/TROUBLESHOOTING.md)
- [GitHub 同类项目比较与优化路线](docs/COMPARISON.md)
- [如何安全地分享给别人](docs/SHARING.md)
- [开发与测试](CONTRIBUTING.md) · [更新记录](CHANGELOG.md)

## 验证与打包

```powershell
node --test
node scripts/smoke.mjs
node scripts/package-share.mjs
```

最后一条生成 `dist/local-readonly-files-mcp-0.2.0.zip` 和 SHA-256 校验文件。打包使用明确的文件白名单，不包含 `.tunnel-client`、旧的 `tools` 目录、运行日志、可执行程序或任意新增文件。安全扫描不是万能的，发送前仍需检查分享包。

Node 实现尚未选择开源许可证，保持 `private: true` / `UNLICENSED`，不会自动发布到 npm。`private` 是 npm 发布设置，不表示 GitHub 仓库是私有的。授权说明见[分享说明](docs/SHARING.md)。
