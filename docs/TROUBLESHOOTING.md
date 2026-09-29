# 常见问题与排障

按“本机程序 → Tunnel → ChatGPT”依次查，避免把解析失败当成账号问题。

| 现象 | 先检查什么 | 处理 |
| --- | --- | --- |
| `node` 找不到 | Node 是否已安装、终端是否重新打开 | 重开终端；客户端配置可填 Node 绝对路径 |
| `npm.ps1` 禁止运行 | PowerShell 策略 | 本项目可直接用 `node --test` / `node scripts/smoke.mjs`，不需要改全局策略 |
| Tunnel 脚本被拦截 | 脚本来源和本机策略 | 先审阅脚本；按下节区分 Restricted 与下载标记，不降低整机策略 |
| 直接启动 index.mjs 没输出 | 是否已提供 root、是否接入 MCP 客户端 | stdio 会等待 JSON-RPC，不会弹出网页；先跑 smoke |
| Root / 文件不存在 | 配置使用的目录是否已被移动或改名 | 重新指定现有目录；旧 profile 的绝对路径不会随目录名自动修改 |
| 文件明明有却看不到 | 是否落在排除规则、链接目录或当前层之外 | 用 list_files 的 path 浏览子目录；不要绕过敏感过滤 |
| `Absolute paths are not allowed` | 工具参数是否误传磁盘绝对路径 | 改为授权目录下的相对路径 |
| `protected as sensitive` / 链接被拒绝 | 文件是否是敏感路径或目录联接 | 只将确认可共享的普通文件副本放入专用目录 |
| 字符乱码 / encoding error | 是否 GBK、无 BOM UTF-16 或二进制 | 在原应用另存为 UTF-8 副本；不要直接改扩展名假装转换 |
| PDF 空白/漏字/扫描件失败 | 文档是否需要 OCR、字体映射 | 使用专业转换，见[格式限制](FORMATS.md) |
| 搜索没结果但文件里确实有 | 查询是正文还是文件名、是否跳过或截断 | 查看 skipped/scan_truncated，缩小 path 后直接读取目标文件 |
| ChatGPT 没有这个工具 | 新会话是否启用连接、权限是否允许 | 选中连接；检查是否发现三个工具；刷新旧工具定义 |
| Tunnel 不显示/权限错误 | 平台组织、目标工作区是否关联 | 按官方权限说明核查；本服务不能替你解除组织限制 |
| 连接发现超时 | tunnel-client 是否仍运行、网络是否正常 | 先 doctor，再 run，保留窗口看错误；不要先重建所有密钥 |
| doctor 成功但读取失败 | root 内实际文件路径、解析限制 | 看具体工具错误，doctor 不会证明所有文件都能解析 |
| 同名 profile 已存在 | 是否重复执行 init | 通常直接 doctor/run；要改目录时用新的 profile，避免覆盖旧配置 |

## Windows 提示“禁止运行脚本”

先运行 `Get-ExecutionPolicy -List`。如果是组织的 MachinePolicy/UserPolicy 限制，联系管理员，不要绕过。只有你有权执行该脚本、已检查源码且不是组织强制限制时，才考虑仅在这一次子进程中允许本地脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File .\scripts\tunnel.ps1 -Action run -ClientPath "D:\Tools\tunnel-client\tunnel-client.exe"
```

这不会修改当前用户或整机的持久策略。若脚本来自下载且被标记为远程，RemoteSigned 仍可能要求签名；确认可信后可以只解除 `scripts/tunnel.ps1` 的下载阻止，或让管理员提供签名版本。不要对整个下载目录批量解除限制。有关作用域与下载标记，见 [Microsoft 官方执行策略说明](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1)。

不涉及密钥的 init 也可以直接用 Node：

```powershell
node scripts/tunnel.mjs init --client "D:\Tools\tunnel-client\tunnel-client.exe" --tunnel "tunnel_YOUR_ID"
```

doctor/run 的 Node 入口要求由秘密管理工具提供 `CONTROL_PLANE_API_KEY` 环境变量，不会弹出隐藏输入提示。

## 启动器可选参数

`-Profile` 选择配置名，`-ProfileDir` 选择配置目录，默认使用当前项目 `.tunnel-client`。init 时才接受 `-Root` 与 `-TunnelId`。如果 init 用了自定义名称/目录，之后每条命令都应保持一致。

`-NonInteractive` 不提示密钥；环境中没有 `CONTROL_PLANE_API_KEY` 就报错。这是为已有秘密管理方案准备的，不会帮你保存密钥。不要在聊天里粘贴环境变量值。

## 停止与恢复

手动 run：Ctrl+C 停止，不需要删除 profile。恢复时同 profile 再 run。不要杀死所有 Node 进程，那可能影响其他项目。

不再使用时，断开 ChatGPT 连接、停止自己启动的 Tunnel，再按自己的凭据管理流程撤销不再需要的密钥/权限；删除代码文件不等于撤销云端授权。本版不安装计划任务，因此没有自动创建的任务需要卸载。

## 反馈问题请提供

- 系统、Node 版本、服务版本（`node src/index.mjs --version`）。
- 本机 smoke 的结果；属于安装、解析、Tunnel 还是 ChatGPT 问题。
- 去掉个人路径、账号、密钥后的错误文字和最小虚构样例。

不要直接发送整个 profile、进程环境、业务原件或完整密钥页截图。
