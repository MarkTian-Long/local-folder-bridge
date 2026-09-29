# 开发与验证

先读 [安全边界](docs/技术说明与安全边界.md)。默认只读、目录本机授权、逐项审批、不提供 shell 是开发约束，不靠提示词维持。日常程序用 Python 标准库；PDF 提取器和测试工具为可选依赖。

## 开发环境

需要 Python 3.11+。以下在本目录的 PowerShell 运行，不要求激活脚本或改变执行策略：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt pypdf==6.18.1
.\.venv\Scripts\python.exe app.py --version
.\.venv\Scripts\python.exe tools/run_tests.py
.\.venv\Scripts\python.exe tools/verify_delivery.py
```

Linux 用 `.venv/bin/python` 替换 `.venv\Scripts\python.exe`。不要把整个程序目录授权给服务；测试临时目录必须在程序目录和正式状态目录之外。Windows 测试父目录默认是用户目录下 `LocalFolderBridge-TestRuns`，可用 `LFB_TEST_PARENT` 指定另一个普通、非敏感位置；测试只删除其新建的临时子目录。

开发依赖使用顶层固定版本，目前未锁定全部传递依赖的哈希。不要把它称为完全可重现的软件供应链；进一步发布前可做带哈希锁文件与依赖漏洞检查。

## 模块导航

| 模块 | 职责 / 改动后重点验证 |
| --- | --- |
| bridge/security.py | 路径、根目录、链接、硬链接、句柄最终路径；必须增加越界正反例 |
| bridge/engine.py | 读取/检索/缓存，提案、审批、备份/恢复；验证冲突及中断后的状态 |
| bridge/extractors.py | 不可信文档解析；保留大小、时间和输出限制，不执行文档脚本 |
| bridge/protocol.py | MCP tools-only 适配；保持输入校验、输出 Schema、工具注解一致 |
| bridge/http_server.py | loopback 管理与 MCP listener 分离；Host/Origin/认证与限额 |
| bridge/tunnel.py / windows.py | 外部进程、脱敏、用户可选 DPAPI；不把密钥写入参数或测试日志 |
| bridge/downloads.py | 官方来源、版本与哈希、归档安全；默认测试使用替身下载 |
| app.py / web/ | 生命周期、管理页面；不改现有账号，不让模型修改授权 |
| tools/package.py | 发布白名单；新增模块、文档和测试文件必须在这里审核登记 |

## 界面检查与手册

先安装开发依赖，再选择获准的 Chromium/Edge 可执行文件。例如 Windows 已安装 Edge 时：

```powershell
$env:CHROMIUM_EXECUTABLE='C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
.\.venv\Scripts\python.exe tools/test_browser.py --native-only
.\.venv\Scripts\python.exe tools/build_manual.py
```

浏览器使用独立临时配置、合成资料和随机 loopback 端口，不使用登录中的浏览器。`--native-only` 不允许以 DOM 适配模式冒充原生导航通过；管理员策略阻断应记为限制。原生文件夹对话框和真实 Tunnel 不属于此套测试。

先编辑 `docs/操作手册.md`，再生成 `使用手册.html`，不要直接编辑生成 HTML。手册旧截图仍明确标记为历史 Linux 样本，新浏览器截图在 `reports/current/screenshots/`。

## 发布验证

```powershell
.\.venv\Scripts\python.exe tools/package.py
```

默认输出到上级目录 `dist/LocalFolderBridge-1.1.1.zip`，附 `.zip.sha256` 与 `.zip.checks.json`。换版本只改 `bridge/__init__.py` 后同步手册和变更记录。不要把 `.venv`、runtime、third_party、reports 或用户状态放进白名单。

把 ZIP 解压到一个新的普通目录，用同一 Python 执行其中的 `tools/verify_package.py` 和 `tools/run_tests.py`。清单只校验**发布文件字节**，不是数字签名、杀毒或对文件来源的担保；源码被有意修改后校验失败是正常的。本开发目录保留原始导入清单供溯源，不更新它来伪造“原包未修改”。

`run_tests.py`、`verify_delivery.py`、`test_browser.py` 支持 `--report-dir`。报告默认在 `reports/current/`，不进入发布包；旧报告只作历史证据。人工发布前再做一次真实 ChatGPT 随机字符串读取验收，并单独记录日期/版本/结果，不能只写“全部测试通过”。
