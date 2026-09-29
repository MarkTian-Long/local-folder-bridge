# 外部组件与来源

本次 ZIP 不包含 Python Windows 运行时、tunnel-client 可执行文件、cloudflared、pypdf wheel 或任何字体文件。软件启动/用户点击安装时才从明确的官方发布来源下载组件，并保留压缩包内相应许可文件或 `.dist-info`。

| 组件 | 使用方式 | 一手来源 |
|---|---|---|
| Python 3.13.15 Windows embeddable | 无合适本机 Python 时由 START.cmd 下载；固定 SHA-256 | https://www.python.org/downloads/release/python-31315/ |
| OpenAI tunnel-client | 用户明确点击后取得官方完整 Windows 资产；校验官方 digest / SHA256SUMS | https://github.com/openai/tunnel-client/releases/latest |
| pypdf 6.18.1 | 可选文字层解析；固定 wheel 与 SHA-256 | https://pypi.org/project/pypdf/6.18.1/ |
| Model Context Protocol | 按已声明版本实现工具子集；不是随包分发完整官方 SDK | https://modelcontextprotocol.io/specification/2025-11-25/basic/transports |

交付环境使用 Playwright、Chromium、pytest、pytest-cov 和 jsonschema 做开发测试，没有随包分发其二进制。开发环境恰有 pypdf 5.9.0，测试报告明确记录，不作为 6.18.1 已验证的替代证据。

本项目新增代码适用根目录 LICENSE；外部组件适用其各自分发许可，不因为本项目许可证而改变。重新分发下载后的离线组件包时应同时保留组件自身的许可及归属文件。
