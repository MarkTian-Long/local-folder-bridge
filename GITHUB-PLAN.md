# GitHub 发布流程与状态

仓库：[MarkTian-Long/local-folder-bridge](https://github.com/MarkTian-Long/local-folder-bridge)，所有者于 2026-09-29 创建并明确选择 Public。本文件保留发布门槛；具体提交和 CI 结果以仓库历史与 [Actions](https://github.com/MarkTian-Long/local-folder-bridge/actions) 为准，不能把配置存在当作验证通过。

## 第一关：来源与授权

保留 `LocalFolderBridge/LICENSE` 原有 MIT 内容和版权声明；它不自动为另一套 Node 代码提供许可。Node 仍是 UNLICENSED，公开前需由所有者确定授权方式。原 ZIP 来源和 SHA-256 见图形界面版复核文档。

仓库所有者、名称和公开可见性已由所有者确认。Node 许可证仍保持现状，不因上传 GitHub 自动改成 MIT。真实账号接入、安装器和跨平台验证仍分别验收。

## 第二关：干净源码快照

不要整体压缩运行目录上传，也不要直接 `git add .`。首批提交范围应为：

1. `scripts/package-share.mjs` 的 `SHARE_FILES` 列出的 Node 文件。
2. `LocalFolderBridge/tools/package.py` 的 `SHARE_FILES`，加上 `LocalFolderBridge/` 前缀。
3. 仓库专用 `.gitattributes`、`.github/workflows/ci.yml`、两个反馈模板、`PROJECT.md`、`GITHUB-PLAN.md`、根 `SECURITY.md`。

建议从两个校验过的 ZIP 提取源码快照，再加入上述仓库专用文件。保留运行目录，不复制 `.tunnel-client`、旧 `tools/`、运行时、虚拟环境、SQLite、DPAPI、日志、历史报告或业务资料。白名单和凭证形状扫描不能代替人工审查；泄露后删文件也不等于从 Git 历史移除，必须撤销凭证。

独立版本标签建议为 `node-v0.2.0` 与 `lfb-v1.1.1`，暂不强制同步。首次提交前审查每个文件的 diff 并重新跑测试。

## 第三关：本机验证

- Node 单测、stdio smoke、白名单打包、解压后重测。
- Python 回归及跳过项、Schema/真实进程生命周期、Windows 浏览器验收。
- Markdown 更新后生成 HTML；生成 ZIP，独立解压，核对 MANIFEST，再执行回归。
- 发布脱敏复核摘要，不附 `reports/` 原始日志和任何账号数据。

## 第四关：推送与远端 CI

只向上述确认的目标仓库添加 remote/push。工作流测试 Windows/Linux 上 Node 22/24、Python 3.11/3.13；Python 分别在无可选 PDF 依赖和安装目标版本后测试，并解压发布包再测。

CI 只有 `contents: read`，不自动发布 npm/PyPI/Release，不使用云端运行密钥；checkout 不持久保存 Git 凭证。Actions 已固定到核对过的完整 commit SHA：

- [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1)
- [setup-node v7.0.0](https://github.com/actions/setup-node/releases/tag/v7.0.0)
- [setup-python v7.0.0](https://github.com/actions/setup-python/releases/tag/v7.0.0)

配置文件不等于 CI 已通过。本机 Windows 结果不代表 Linux 或其他版本已经验证。修改 Actions 的运行环境、并发或发布步骤前应重新核对权限及计费设置。

## 第五关：正式版本发布

- 许可证、贡献来源和远端 CI 确认。
- Windows 测试目录 + 实际 ChatGPT 会话验证随机字符串读取；不要预先把答案放进提示词。
- 明确支持系统、文件格式、未覆盖功能，以及停止服务/撤销授权方式。
- 手工创建版本化 Release，附两个独立 ZIP 和 SHA-256，不附官方运行时 EXE 或个人配置。
- 设置真实可用的安全反馈渠道，不能填写虚构地址或假装已开启私密漏洞报告。

## 优化排序

P1：可选自启动/重连（部署须单独授权）、真实中文文档语料、调用可观测性、依赖锁定和供应链检查。P2：MCP SDK 适配、大目录索引及失效策略、安装器原子升级/回滚。新增解析器必须保留目录边界、超时、输出限额，不执行文档脚本。
