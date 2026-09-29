# 如何安全地分享给别人

## 推荐交付方式

运行下面三条命令，在全部成功后发送生成的 ZIP 和同名 `.sha256` 文件即可：

```powershell
node --test
node scripts/smoke.mjs
node scripts/package-share.mjs
```

输出：`dist/local-readonly-files-mcp-0.2.0.zip`，包内有完整手册和无敏感内容的示例。重复打包会更新同版本的生成产物；源文件不变时 ZIP 字节可复现。`SHARE-MANIFEST.json` 保存每个源文件的 SHA-256，ZIP 旁边的校验文件用于传输后核对。校验和证明文件一致性，不等于作者身份或恶意软件认证。

**不要用资源管理器把整个旧项目文件夹压缩发出去。** 白名单在 `scripts/package-share.mjs`，不会自动收录新文件，因此即使在 docs 下临时放了私人笔记也不会被带走。新增正式文档时应审核后再加入白名单。

## 不会包含什么

`.tunnel-client` 配置/健康检查文件、旧 `tools` 目录及其中程序、个人 API key、`.env`、运行日志、任意未列入白名单的材料都不被自动收录。打包器会对待分享文本扫描常见 key 和 Tunnel ID 形状，发现后停止且不打印内容。

但是你如果把其他格式的秘密写进 README 或源代码，扫描不一定识别；发送前仍需抽查。**示例验证码也要恢复为虚构内容，不要放真实口令。**

## 接收者须知（可复制发送）

> 这是一个本地文件只读 MCP，先安装 Node.js，解压后打开 README。无需密钥即可运行 `node scripts/smoke.mjs` 验证本机程序。要接网页版 ChatGPT，请按 docs/CHATGPT.md 创建自己的 Tunnel 和连接，只授权准备给 AI 使用的文件夹。本包不含账号密钥；不提供扫描件 OCR，也不能保证复杂 PDF/Excel 的提取保真。不要把敏感文件放进授权目录。

## 分享前检查清单

- [ ] 本机 `node --test` 和 smoke 通过。
- [ ] 在新的解压目录再次运行 smoke，确认不依赖作者机器的旧文件。
- [ ] ZIP 不包含私有 profile、日志、可执行程序、真实账号/路径或秘密。
- [ ] README 中的能力与限制同实际代码一致。
- [ ] 接收者知道必须配置自己的授权目录和账号，而不是继续使用作者的 Tunnel。
- [ ] 明确试用范围与软件授权方式。

## GitHub 已公开，软件授权与 npm 发布仍分开

源码已发布到 [公开 GitHub 仓库](https://github.com/MarkTian-Long/local-folder-bridge)，但没有替作者选择 Node 的开源许可证；`package.json` 保持 `private: true`、`license: UNLICENSED`，也没有发布 npm 或正式 Release。GitHub 可见性与软件许可不同，这不是 MIT/Apache 开源授权。作者可明确授权特定接收者试用；扩大开源授权前仍需决定许可条款并加入 LICENSE。Python 子目录保留其独立 MIT LICENSE，不自动覆盖 Node。

日常更新遵循 [推送与同步手册](https://github.com/MarkTian-Long/local-folder-bridge/blob/main/GITHUB-SYNC.md)。提交前检查明确的文件清单和 diff，不要仅依赖 `.gitignore`：它不会让已经被提交过的密钥从历史中消失。推送会触发自动检查，但本地修改不会自动上传，用户安装的服务也不会自动升级。
