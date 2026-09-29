# 新手安装：先验证本机，再接 AI

这是一个“小型本地文件服务”，不带聊天窗口。AI 通过它请求某个文件；它检查授权范围后返回文本。双击 `.mjs` 文件不是安装步骤。

## 1. 准备环境

安装 [Node.js 官网](https://nodejs.org/)当前受支持的 LTS（代码最低要求 20），解压分享包，在含 `package.json` 的文件夹打开终端。下面的路径只是示例，按自己的位置替换：

```powershell
Set-Location "D:\MCP\local-readonly-files-mcp-0.2.0"
node --version
node src/index.mjs --version
```

最后应输出 `0.2.0`。macOS/Linux 本机服务使用相同 Node 命令，替换为系统实际路径即可；完整跨平台验证需在目标系统另行运行测试。Windows Tunnel 辅助脚本只适用于 PowerShell。

## 2. 不联网的样例验收

```powershell
node scripts/smoke.mjs
node --test
```

不需要 `npm install`、密钥或登录。smoke 只读包内 `examples/files`，验证列目录、读取、搜索和越界拒绝。测试会创建并清理系统临时目录中的虚构文档，不修改业务文件。

看到 `PASS` 后：网页版用户去 [ChatGPT 接入](CHATGPT.md)；本地 MCP 客户端用户继续下面的配置。

## 3. 接本地 MCP 客户端

[配置模板](../examples/stdio-client.json)使用常见 `mcpServers` 结构，但各客户端格式可能不同。将代码路径与授权目录改成自己的绝对路径，按客户端说明导入。Windows JSON 路径建议用 `/`，避免反斜杠转义问题。

| 配置 | 示例 | 含义 |
| --- | --- | --- |
| 程序 | `node` | JavaScript 运行环境；找不到时填 Node 的绝对路径 |
| 第一个参数 | `D:/MCP/local-readonly-files-mcp-0.2.0/src/index.mjs` | 服务代码的位置 |
| 第二个参数 | `--root` | 明确声明授权目录 |
| 第三个参数 | `D:/MCP/local-readonly-files-mcp-0.2.0/examples/files` | 只允许读取这个目录及其子目录 |

本地客户端一般会负责启动和停止服务，不必另开一个同样的 Node 窗口。

## 4. 换成自己的资料

新建专用资料文件夹，只复制准备交给 AI 的文件，再将 `--root` 改到那里并重启连接。不要授权整个磁盘。

工具参数使用相对路径，如 `会议/记录.md`，不是 `D:/...`。链接、敏感配置和部分运行目录会被排除，见[安全说明](SECURITY.md)。

## 成功标准

本机 smoke 成功 ≠ Tunnel 在线 ≠ 网页版读取成功。逐项确认：

1. 本机测试通过。
2. Tunnel doctor 检查通过，客户端持续运行。
3. ChatGPT 发现三个工具。
4. 新会话真实调用 `read_file`，读到你临时改写的验证码。

失败时按[排障顺序](TROUBLESHOOTING.md)检查，不必一开始就重建密钥。
