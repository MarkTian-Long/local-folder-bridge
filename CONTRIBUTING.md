# 开发与验证

本页主要说明 Node 只读实现。完整仓库的日常提交、拉取、推送、CI 与失败处理见 [推送与同步手册](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-SYNC.md)；图形版见 [Python 开发说明](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/LocalFolderBridge/DEVELOPMENT.md)。这两个仓库导航不属于 Node 精简 ZIP 的离线文件。

## 项目结构

```text
src/index.mjs           stdio JSON-RPC、路径校验、工具和轻量解析
test/                  协议、权限、格式、分页与分发回归
scripts/smoke.mjs       无凭据的本机端到端验收
scripts/tunnel.mjs     参数化 Tunnel CLI 适配器
scripts/tunnel.ps1     Windows 隐藏输入密钥入口
scripts/package-share.mjs  白名单 ZIP 及完整性清单
examples/              虚构资料与客户端配置模板
docs/                  用户手册、安全边界、比较和分享说明
```

运行依赖只有 Node.js 核心模块，不需要 npm install。测试使用 Node 内置 test runner。MCP 服务只实现本项目所需的 stdio/tools 子集：initialize、ping、tools/list、tools/call；声明支持 2024-11-05、2025-03-26、2025-06-18 协议版本。不支持版本协商时返回本服务最新支持版本，不原样回显未知版本。

没有实现动态 Roots、Resources、Prompts、任务队列、取消请求或 HTTP；不要把“单元测试通过”表述为所有 MCP 客户端的完整兼容认证。

## 修改流程

1. 行为/边界修改先添加能检测缺陷的回归测试，再修复。
2. 保持 stdout 只输出 MCP JSON-RPC 行；运行日志用 stderr。
3. 不扩展默认授权范围，不引入写操作工具。读取正文不能触发文档里的脚本/宏。
4. 同步工具 Schema、返回结构、限制文档和版本信息。
5. 分享文件白名单新增项需要人工检查；不打包本机配置、二进制或业务数据。

```powershell
node --test
node scripts/smoke.mjs
node scripts/package-share.mjs
```

测试在临时目录造数据；ZIP 排除测试会额外放入随机假秘密检查是否被打包。Windows 上使用目录 junction 来检查链接，其他系统使用 Node 的 symlink 实现。

## 验证层级

- **自动化回归**：协议错误、参数、目录逃逸/敏感路径、分页、各种最小文档样例、分享包和启动参数。
- **本机 smoke**：真实子进程按 MCP 请求/响应读取虚构样例，不联网。
- **离线 Tunnel 配置**：可在临时 profile 目录运行 init，检查带空格/中文路径及不覆盖旧配置；不代表网络连通。
- **真实云端**：需要账号权限和运行时密钥，必须另测 doctor、持续运行、ChatGPT 工具发现、read/search。不要让 CI 使用作者的密钥。
- **格式准确率**：当前测试为最小合成样例，不是大型真实文档兼容数据集。中文 PDF、OCR、复杂表格需要单独验收。

没有实际运行的系统/账号不能写成已验证。修改后建议 Windows、Linux、macOS 及当前受支持的 Node LTS 分别测试，再决定是否增加支持承诺。

## 参考

[MCP 工具规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)说明 Schema、注解及错误约定；[安全文档](docs/SECURITY.md)记录本服务不能保证的边界；[比较文档](docs/COMPARISON.md)记录后续选型，而不是已安装功能。
