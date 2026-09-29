# 网页版 ChatGPT 接入与日常启动

适用：已完成[本机验收](QUICKSTART.md)。核对日期：2026-09-29。页面名称和可用权限可能变化，以 [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) 和 [ChatGPT 开发者接入说明](https://developers.openai.com/plugins/deploy/connect-chatgpt)为准，不能保证所有账号都看到相同入口。

## 原理与边界

```text
ChatGPT → OpenAI Tunnel → 本机 tunnel-client → 本机 MCP → 授权目录
        ←              读取到的文本结果               ←
```

MCP 用 stdio（进程输入/输出）通信，不监听 HTTP 端口；Tunnel 让云端请求抵达本机，默认从本机发起出站连接。它不代表数据不出电脑：返回片段会发给 AI。

本手册是“各自连接各自电脑”，不是多人共用作者电脑。接收者自行管理自己的 Tunnel、密钥和资料目录。

## 1. 准备自己的 Tunnel 和客户端

在 Platform Tunnels 页面创建 Tunnel，关联目标 ChatGPT 工作区，确认账号有使用权限，记录 Tunnel ID。不要把运行时密钥写进聊天、脚本或截图。

从 [OpenAI 官方 tunnel-client 发布页](https://github.com/openai/tunnel-client/releases/latest)下载适合系统的客户端，保留同包组件与说明。分享包不附带该程序。下面的 `D:\Tools\tunnel-client\tunnel-client.exe` 需要换成自己的实际位置。

辅助脚本的 init 参数已对照本机 0.0.13 帮助；新版本先运行 `tunnel-client help quickstart` 确认兼容性。

## 2. 生成本机配置，通常只做一次

在项目目录的 PowerShell 中运行，将占位符换成自己的真实 Tunnel ID：

```powershell
.\scripts\tunnel.ps1 -Action init -ClientPath "D:\Tools\tunnel-client\tunnel-client.exe" -TunnelId "tunnel_YOUR_ID"
```

默认授权 `examples/files`，生成新 profile `share-local-files`，保存在项目 `.tunnel-client` 中。这一步只生成本机配置，不会创建云端 Tunnel、不需要密钥，也不会覆盖同名配置。

要授权自己的资料目录，显式提供 `-Root`，并用新 profile 名称：

```powershell
.\scripts\tunnel.ps1 -Action init -ClientPath "D:\Tools\tunnel-client\tunnel-client.exe" -TunnelId "tunnel_YOUR_ID" -Profile "my-notes" -Root "D:\Shared Notes"
```

之后 doctor/run 都带同一个 `-Profile "my-notes"`。`-Root` 只用于 init；运行使用已保存的配置，不能临时传 Root 改范围。

## 3. 检查并启动

```powershell
.\scripts\tunnel.ps1 -Action doctor -ClientPath "D:\Tools\tunnel-client\tunnel-client.exe"
.\scripts\tunnel.ps1 -Action run -ClientPath "D:\Tools\tunnel-client\tunnel-client.exe"
```

两次命令需要密钥时分别出现隐藏输入提示。在提示处粘贴，不要把密钥放在命令行。脚本不回显、不保存密钥；运行时交给子进程环境，退出后恢复原环境。同权限/管理员进程仍可能读取环境变量，它不是保险箱。

`run` 持续运行才正常；不返回命令提示符并非卡死。首轮验证建议保留窗口查看错误。Ctrl+C 停止；本脚本不自动安装后台服务或开机任务。

## 4. 在 ChatGPT 创建连接并验收

按当前官方文档启用开发者模式，在 Plugins/应用区域创建开发者连接，连接方式选 Tunnel，选择自己的 Tunnel。若没有入口，检查账号和工作区政策，不要随意公开本地端口。

发现的工具应有 `list_files`、`read_file`、`search_files`。新建聊天并启用此连接，再用[验证提示词](USER-GUIDE.md#第一次验证)。更新代码后若仍显示旧定义，刷新/重连客户端工具列表。

## 重启、关闭、换电脑

- 关机、睡眠、断网或停止客户端时，网页无法读本机；恢复后仍需启动客户端。
- 配置不必每次重建。脚本默认不保存密钥，没有秘密管理工具注入时，下次启动仍需输入。
- 健康检查使用本机随机端口；ChatGPT 连接 Tunnel，不需要每次重新填写端口。
- 目录改名或移动后，旧 profile 中的绝对路径不会自动变化。生成指向新路径的新 profile 后启动；不要同时让同一个 Tunnel 对应两个不同资料目录。
- 登录自启动可以结合 Windows 任务计划程序与当前用户加密凭据；本版**未实现无人值守密钥存储和任务安装**。不要把密钥直接写入任务参数。

已有旧 `local-files` profile 的用户可以传 `-Profile local-files`，但先确认其中路径仍有效。旧 `tools/secure-key-handoff.mjs` 属于个人测试遗留工具，不包含在分享包内；新用户按本手册配置。
