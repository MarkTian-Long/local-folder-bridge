# Local Folder Bridge · 本机文件桥 1.1.1

Windows 联网启动包。让 ChatGPT 通过官方 MCP 隧道读取你授权的本机文件夹；文件写入、移动、新建目录和程序回收可选开启，实际操作逐项在本机审批。默认只读；不提供远程 shell、鼠标控制或远程目录扩权。

## 开始使用

完整解压本包 → 双击 `START.cmd` → 授权一个非敏感测试目录 → 本机浏览并读取 → 在“连接与诊断”安装官方 tunnel-client、填写 Tunnel ID 与运行密钥 → 启动隧道 → ChatGPT 绑定同一个 Tunnel 并刷新工具 → 使用随机验证文件验收。

没有合适的 Python 时，启动器尝试下载固定官方 Windows 运行环境并验证 SHA-256。这里没有内置 Windows EXE 运行时或隧道二进制，不是完全离线安装器。无需逐个复制源码、安装 Node.js 或手工编译。

**先双击 `使用手册.html` 阅读完整步骤。** 该 HTML 内含说明与截图，可离线打开；截图是隔离测试资料的 Chromium 渲染，不是你的 Windows 电脑截图。

## 文件入口

| 文件 | 内容 |
|---|---|
| [使用手册.html](使用手册.html) | 从启动、配置到文件操作、恢复、故障排查 |
| [docs/操作手册.md](docs/操作手册.md) | 手册的可编辑 Markdown 正文 |
| [docs/插件配置说明.md](docs/插件配置说明.md) | 旧“本地文件（只读）”插件的处理规则 |
| [docs/技术说明与安全边界.md](docs/技术说明与安全边界.md) | 架构、工具输入输出、数据和安全限制 |
| [docs/测试与验收报告.md](docs/测试与验收报告.md) | 已执行测试、实际覆盖率和未验收项 |
| [docs/本机复核与发布准备.md](docs/本机复核与发布准备.md) | 本次 Windows 实测、修复与剩余发布门槛 |
| [DEVELOPMENT.md](DEVELOPMENT.md) / [CHANGELOG.md](CHANGELOG.md) | 开发入口、模块导航与版本记录 |
| `RUN_TESTS.cmd` | 隔离回归，实际数量与跳过项见运行报告 |
| `tools/test_browser.py` | 可选 Playwright 界面测试，需开发依赖 |
| `tools/verify_delivery.py` | JSON Schema、独立进程生命周期验证 |
| `tools/verify_package.py` | 校验本包 MANIFEST.sha256 |

## 当前交付状态

源码已在 [GitHub](https://github.com/MarkTian-Long/local-folder-bridge) 公开，初始提交的 Windows/Linux 多版本 CI 已通过；后续状态看 [Actions](https://github.com/MarkTian-Long/local-folder-bridge/actions)。开发者提交与拉取流程见 [同步手册](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-SYNC.md)。这不是正式 Release，也不会自动升级本机运行的服务。

1.1.1 已在 Windows 上复核 Python 回归、真实 HTTP/MCP/进程重启、原生 Edge 页面交互和合成凭证的 DPAPI。双击引导下载、原生目录选择对话框和真实 ChatGPT/Tunnel 仍需现场验收，不能用本机测试代替。详见本次复核文档。

`docs/测试与验收报告.md` 是原始 1.1.0 Linux 交付记录，旧覆盖率/浏览器结果不作为当前版本证据。本次测试默认写入 `reports/current/`；新发布 ZIP 不包含任何原始测试报告、运行配置或凭证。

本次没有改动你的网页插件配置；先复用有效旧 Tunnel，启动后刷新工具。旧 Tunnel 失效时再更新绑定或新建 Tunnel 连接。**不要把运行密钥发到聊天里。** 平台隧道要求见官方文档：<https://developers.openai.com/api/docs/guides/secure-mcp-tunnels>。

## 数据与风险

文件不必预先整库上传，但被返回的文件文字会传给 ChatGPT。普通文档可能包含未被文件名过滤识别的秘密，必须由你决定哪些资料可共享。删除操作使用程序回收区而非 Windows 回收站；程序不会自动清理原始备份。备份不是完整权限/扩展属性备份，也不是恶意软件隔离沙箱。

配置与备份默认在 `%LOCALAPPDATA%\LocalFolderBridge`，与程序目录分开。升级前正常退出，同名替换程序文件；不要删除状态目录当作普通清理。清除配置/卸载前先归档需要的备份。

本项目源代码授权见 `LICENSE`，外部组件来源与许可说明见 `THIRD_PARTY_NOTICES.md`。交付不含个人凭证、授权资料或字体文件。
