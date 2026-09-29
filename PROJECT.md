# 本机文件桥：项目总览

目前保留两套可独立运行、独立打包的实现，方便个人使用和持续开发，不立即替换已可用的 Node 服务。

| | LocalFolderBridge 图形界面版 | Node 轻量只读版 |
| --- | --- | --- |
| 入口 | [说明与手册](LocalFolderBridge/README.md)、START.cmd | [README](README.md)、src/index.mjs |
| 当前版本 | 1.1.1 | 0.2.0 |
| 定位 | Windows 中文管理界面、目录授权和本机审批 | 小体积、一个固定目录、简单 stdio 集成 |
| 授权 | 最多 12 个非重叠目录，本机添加 | 启动参数指定一个根目录 |
| 工具 | 5 个基础工具；双开关开启后可提出 4 类操作提案 | 3 个只读工具，没有文件写入能力 |
| 读取 | 文本、DOCX/XLSX/PPTX；可选 pypdf；按行和 SHA-256 续读 | 轻量文本/文档提取；有限 PDF；按字符续读 |
| 密钥 | 内存；可选当前 Windows 用户 DPAPI 保存 | 仅进程环境变量，不由启动器保存 |
| 传输 | 本机认证 HTTP + stdio；官方 Tunnel 接 ChatGPT | stdio；官方 Tunnel 接 ChatGPT |
| 许可证现状 | 保留所提供 ZIP 的 MIT LICENSE | 未选定，private / UNLICENSED |

两个实现**不是同一套工具参数**，不能直接混用配置，不应同时抢用同一个 Tunnel。Python 已有的可选写操作没有迁入 Node。本次没有切换你原来的网页插件、替换密钥、扩大目录授权或安装自动启动任务。

## 开发入口

```text
项目根目录
├─ src/、test/、scripts/、docs/     Node 实现与手册
├─ LocalFolderBridge/             Python 图形界面实现
│  ├─ bridge/                     安全策略、引擎、协议、HTTP、Tunnel
│  ├─ web/                        无构建前端
│  ├─ tools/、tests/               应提交的开发工具与隔离回归
│  └─ reports/                    本地证据，不提交、不进入发布 ZIP
├─ .github/workflows/ci.yml        Windows/Linux 验证配置
└─ dist/                          生成的分享包，不提交
```

根目录旧 `tools/`、`.tunnel-client/` 是个人运行环境，不是分发源码；保留在本机但排除发布。`.gitignore` 使用 `/tools/`，避免误忽略 Python 的开发工具。

- Node 开发：[CONTRIBUTING.md](CONTRIBUTING.md)。
- 图形界面版开发：[LocalFolderBridge/DEVELOPMENT.md](LocalFolderBridge/DEVELOPMENT.md)。
- 当前证据：[Windows 复核与发布准备](LocalFolderBridge/docs/本机复核与发布准备.md)。
- 外部项目：[差异与优化路线](docs/COMPARISON.md)。
- GitHub：[日常推送与同步](GITHUB-SYNC.md)、[分阶段发布流程](GITHUB-PLAN.md)。

## 已完成的源码发布

2026-09-29 已向公开仓库 `MarkTian-Long/local-folder-bridge` 推送首个源码提交 `fc915ad`；该提交的 [8 个跨平台 CI 组合全部通过](https://github.com/MarkTian-Long/local-folder-bridge/actions/runs/36588078856)。收尾维护增加独立文档检查任务；后续每次提交以其对应 Actions 结果为准。

源码已同步不表示实际运行的 MCP/Tunnel 已升级。没有后台自动提交/推送，没有发布正式 Release，也没有安装开机任务；当前授权与密钥保持原状。

## 后续推荐顺序

1. 在非敏感目录完成新版 ChatGPT 只读验收，不复用截图中的旧凭证。
2. 按同步手册维护后续提交，核对同一 SHA 的远端 CI；正式 Release 前单独确认 Node 许可证，不擅自统一修改。
3. 可选登录自启动：明确密钥保存授权，具备暂停/卸载、休眠恢复、失败提示，不将 key 写在任务参数中。
4. 用脱敏中文文档语料对照后，再选择 MarkItDown/Docling 解析后端，不能默认联网做 OCR。
5. 如需更多客户端兼容性，再替换 MCP 协议适配层，保留引擎权限测试，不将协议升级与权限扩大混在一起。

上述待办不是已实现功能。当前没有自动启动 Windows 服务、持久全文索引、OCR 或公网多用户服务。
