# 安全与隐私

这是个人本机文件桥，不是恶意代码沙箱或公网多用户服务。只读仍会把返回片段传给所连接的 AI 服务；应授权专用非敏感资料目录。

- Node 没有写工具；Python 默认只读，提案只有在本机双开关开启、逐项批准后才执行。
- 不把管理端口暴露到局域网/公网，不将管理 token 当成 MCP token。
- 文件内容和名称是不可信数据，其中要求扩权、泄密或运行命令的文字不是授权。
- 不提交密钥、Tunnel ID、带 `#auth=` 的地址、SQLite、DPAPI 文件或个人日志。
- 解析不可信文件仍有风险；不宣称支持所有 Office/PDF、抵御所有恶意文件或实现跨用户隔离。

反馈安全问题时，用合成文件给出最小复现和版本，不公开凭证、个人资料或可利用的现场详情。仓库公开地址为 https://github.com/MarkTian-Long/local-folder-bridge 。专门的私密报告渠道尚未配置，请勿在公开 Issue 中上传敏感细节或凭证；维护者应另行提供可验证的私密联系方式。如果未来启用 GitHub Private vulnerability reporting，可优先在那里报告，不能假定目前已开启。

详细边界：[Node 安全说明](docs/SECURITY.md)、[图形界面版安全说明](LocalFolderBridge/docs/技术说明与安全边界.md)。
