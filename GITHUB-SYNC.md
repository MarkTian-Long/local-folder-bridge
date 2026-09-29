# 日常开发、推送与同步

适用仓库：[MarkTian-Long/local-folder-bridge](https://github.com/MarkTian-Long/local-folder-bridge)。本页是完整 Git 仓库的维护流程，不是分享 ZIP 的使用说明。

## 目前哪些会自动执行

| 环节 | 当前机制 | 不会自动做什么 |
| --- | --- | --- |
| 本地源码 ↔ GitHub | Git `origin` 远程与 `main` 跟踪分支；维护者明确执行 fetch/commit/push | 不后台上传、不自动提交、不强制覆盖双方改动 |
| 推送后的验证 | 每次 push、PR 和手动运行触发 `.github/workflows/ci.yml` | 检查失败不会自动撤销已经推送的提交 |
| 文档一致性 | `docs` 检查内部文件链接、关键版本标签，以及 Markdown 重新生成的 HTML | 不抓取外部网址、不检查页内锚点、不保证文字语义正确 |
| 程序回归 | Windows/Linux × Node 22/24 与 Python 3.11/3.13，共 8 个组合 | 不使用真实 Tunnel/key，不代表 ChatGPT 现场验收 |
| 分发包 | 两套白名单打包器生成 ZIP 与 SHA-256；CI 验证打包，Python 还解压重测 | 不上传 Release、不发布 npm/PyPI，不更新别人的安装目录 |

**源码同步、使用者升级和本机服务自启动是三件不同的事。** GitHub 收到源码不会自动替换正在运行的程序，电脑重启也不会因此启动 MCP/Tunnel。当前没有安装自动同步或自启动任务。

## 1. 修改前先确认分支与远端

在包含根 `package.json` 和 `LocalFolderBridge/` 的项目根目录运行：

```powershell
git status --short --branch
git remote -v
git branch -vv
git fetch origin
git rev-list --left-right --count HEAD...origin/main
```

最后一条输出依次是“仅本地有 / 仅远端有”的提交数。`0 0` 表示已同步。`fetch` 更新远端状态，不覆盖工作文件。

只有在**当前为 main、工作区和暂存区干净、仅落后远端**时，才执行 `git merge --ff-only origin/main`。双方都有新提交、存在本地修改或 Git 提示冲突时先停下审查，不执行强推、硬重置或自动覆盖。Fork/分支贡献者以自己的远端和 PR 为准，不照搬作者的 main 推送命令。

## 2. 修改与本机验证

- 修改 Node 行为时同步根 README、`docs/`、CHANGELOG 和工具 Schema。
- 修改图形版手册时先编辑 `LocalFolderBridge/docs/操作手册.md`，再运行生成器；不要只改 HTML。
- 改版本时以 `package.json` 和 `LocalFolderBridge/bridge/__init__.py` 为来源，同步两套说明和 `PROJECT.md`，不要求两套版本相同。
- 新文件需审查后明确 `git add -- 文件路径`；需要进入分享 ZIP 的文件还须加入各自的 `SHARE_FILES`。两份白名单不会自动收录新文件。

首次建立 Python 开发环境见 [图形版开发说明](LocalFolderBridge/DEVELOPMENT.md)。下面假设已按该说明创建 `.venv` 并安装开发依赖，在仓库根目录逐条执行；**任一步非零退出就停止，不继续提交**：

```powershell
node --test
node scripts/smoke.mjs
node scripts/package-share.mjs
.\LocalFolderBridge\.venv\Scripts\python.exe .github/test_check_docs.py
.\LocalFolderBridge\.venv\Scripts\python.exe .github/check_docs.py
.\LocalFolderBridge\.venv\Scripts\python.exe LocalFolderBridge/tools/build_manual.py
.\LocalFolderBridge\.venv\Scripts\python.exe LocalFolderBridge/tools/run_tests.py
.\LocalFolderBridge\.venv\Scripts\python.exe LocalFolderBridge/tools/verify_delivery.py
.\LocalFolderBridge\.venv\Scripts\python.exe LocalFolderBridge/tools/package.py
git diff --check
```

文档检查读取 Git 已跟踪/暂存的文件名及其**工作区内容**；新文档应在人工检查后逐个加入暂存区再检查。它不审计提交历史、不代替凭证扫描或 staged diff 审查。Linux 将 `.venv\Scripts\python.exe` 换为 `.venv/bin/python`。

需要界面验证时另按 DEVELOPMENT.md 运行 `test_browser.py --native-only`；正式分发前仍须解压 ZIP 重测，以及实际 ChatGPT 随机字符串验收。纯文档提交不等于服务端版本已经升级。

## 3. 审核、提交、推送

逐个暂存本次文件，不用 `git add .`。例如这次只改根 README 时：

```powershell
git add -- README.md
git diff --cached --name-status
git diff --cached --check
git diff --cached
git status --short
```

确认没有密钥、实际 Tunnel ID、私人文档/路径、`.tunnel-client/`、根 `tools/`、运行时、日志、`.venv/`、状态库或 `dist/`。不要因 `.gitignore` 存在就跳过审查；已跟踪文件不受它保护。发现疑似秘密时只记录文件/位置，不粘贴内容。

确认本次发布授权、当前分支为 main、目标仍是本仓库后：

```powershell
git commit -m "docs: update usage guide"
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
git status --short --branch
```

两处 SHA 相同才表示远端收到该提交；再去 [Actions](https://github.com/MarkTian-Long/local-folder-bridge/actions) 核对**同一 SHA** 的 9 个任务（1 个文档任务 + 8 个程序组合）。不能用上一次绿色结果证明本次成功。此流程未安装 Git hooks/分支保护，不是禁止所有绕过的强制门禁。

## 4. 失败、回滚和交接

- 推送提示远端领先：重新 fetch、审查双方差异；不加 `--force`。
- 网络中断、结果不明：先 `git ls-remote` 核对提交，避免凭感觉重复操作。
- CI 失败：查看失败任务，修复后新建提交再推送；不要删除失败证据或减弱测试来变绿。
- 已公开的错误提交：经审查用 `git revert <目标提交>` 创建可追溯的撤销提交，不重写共享历史；疑似密钥泄漏应立即撤销密钥，revert 不能清除历史中的秘密。
- 使用者升级：先正常停止程序/Tunnel，保留配置与备份；部署新文件、核验、重启并重新验收。不能把 Git 同步当成运行服务的热更新。

交接最少记下：改了什么、本机检查及跳过项、提交 SHA、远端是否一致、对应 CI 链接、尚未现场验收的项目。正式 Release 另按 [发布流程](GITHUB-PLAN.md) 处理；不因源码仓库公开就改变 Node 的 UNLICENSED 授权。
