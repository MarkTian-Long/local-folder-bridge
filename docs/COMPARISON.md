# GitHub 同类项目比较与优化路线

调研日期：2026-09-29。依据上游官方仓库 README/工具说明、本机 Node 源码及用户提供的 LocalFolderBridge ZIP；不是吞吐量、解析准确率或安全性排名，没有安装这些外部项目做横向跑分。上游 main 会继续变化。

## 结论

本项目适合“给个人一个轻量、中文说明完整、只读一个目录的本地文件入口”。不要为了格式数量把它描述成完整文档解析平台。优先提升安全边界、结果可信度和可安装性；复杂文档解析适合做可选后端。

## 选型比较

| 项目 | 主要能力与定位 | 与本项目的关键差异 | 值得借鉴/何时选择 |
| --- | --- | --- | --- |
| [MCP 官方 Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) | 文件系统操作、目录授权、动态 Roots、批量读取、文本/媒体读取，也提供写入/编辑/移动工具 | 它的 search_files 是路径模式匹配；本项目是正文短语搜索。本项目固定一个 root，只暴露三个只读工具 | 需要通用文件操作或丰富客户端适配时研究它；若必须只读，不能只靠提示词禁止写入，需要额外权限/只读挂载 |
| [Microsoft MarkItDown MCP](https://github.com/microsoft/markitdown/tree/main/packages/markitdown-mcp) | 通过 MarkItDown 将文件/URI 转 Markdown，提供 convert_to_markdown；支持 stdio 与 HTTP 模式 | Python 转换生态，格式提取更专门；其 README 提醒默认没有认证，并能按运行用户权限访问文件/网络。本项目有单目录边界、不接收任意 URL | 优先评估为可选本地文档转换后端；不要直接替换服务后误以为仍有本项目的目录隔离 |
| [Docling MCP](https://github.com/docling-project/docling-mcp) | 结构化文档转换、缓存，可配置 OCR/表格处理；有本地及远端转换模式 | 依赖和部署复杂度更高，适合认真处理复杂文档；本项目仍是轻量提取，无 OCR、无持久索引 | 对扫描件/表格/结构保真有更高要求时试验；需显式选择本地转换并检查模型依赖与缓存隐私 |
| [DesktopCommanderMCP](https://github.com/wonderwhy-er/DesktopCommanderMCP) | 文件操作、终端、进程等桌面开发能力 | 能力范围更广；上游明确提醒终端能力不受文件工具 allowedDirectories 同样限制。本项目不暴露 shell | 借鉴可观测性和操作体验，但不能把其允许目录设置理解为整台机器的沙箱 |
| 本项目 0.2.0 | Node 核心模块、固定目录、列表/读取/正文搜索、中文手册与离线示例 | 上手依赖少，功能范围清楚；手写协议/解析器覆盖有限，不是成熟全文检索或完整沙箱 | 小规模个人资料读取、教学验证、明确边界的试用分享 |
| 用户提供的 LocalFolderBridge，本轮维护为 1.1.1 | Python 标准库、Windows 中文 UI、多目录、本机逐项审批、可选 DPAPI、可选 pypdf | 面向日常管理更完整；维护代码和权限流程更多。与 Node 工具参数不兼容，当前仍是受限协议适配层 | 保留为图形界面路线；先验证只读和发布工程，复杂解析/自启动后续单独验收 |

相关上游原文：[Filesystem README](https://raw.githubusercontent.com/modelcontextprotocol/servers/main/src/filesystem/README.md)、[MarkItDown MCP README](https://raw.githubusercontent.com/microsoft/markitdown/main/packages/markitdown-mcp/README.md)、[Docling MCP README](https://raw.githubusercontent.com/docling-project/docling-mcp/main/README.md)。

## 本轮已落实

1. 明确工具只读标记和调用用途，提供结构化结果与输出 Schema。参考 [MCP 工具规范](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)，不宣称实现全部协议能力。
2. 子目录列表/搜索、分页、续读信息和搜索漏扫提示，避免把截断结果误认为全部内容。
3. 隐藏 Tunnel/代理配置、拒绝链接和路径别名绕过，弱化绝对路径泄露，校验参数和请求封装。
4. 修复 Excel 空列错位、文本乱码静默替换；为 PDF 增加累计展开预算并明确有限支持。
5. 参数化启动器、隐藏密钥输入、本机 smoke 示例、白名单 ZIP 与校验清单，移除分享流程对作者路径/账号的依赖。
6. Python 路线修复 GBK 环境回归、重复启动错误弹页、打包私有文件泄漏与清单校验；复测原生 Windows DPAPI、Edge UI 与进程生命周期。保留 1.1.0 报告为历史来源，不与当前结果混用。

## 下一步建议（尚未实现）

| 优先级 | 改进 | 验收标准与代价 |
| --- | --- | --- |
| P1 | 可选 MarkItDown/Docling 解析适配器 | 先用一批脱敏中文 PDF、扫描件、合并单元格、公式表和复杂 DOCX 与人工原文对照；有明确失败/置信提示；所有输入先过现有路径校验；不允许适配器自行联网或扩范围 |
| P1 | 运行生命周期与可选登录自启动 | 明确保存密钥授权，使用当前用户加密存储；验证重启/休眠恢复、单实例、日志脱敏、暂停及卸载；不能把 key 放到任务参数中 |
| P1 | 隔离与协议兼容 | 低权限运行/只读挂载验证；考虑官方 MCP SDK，覆盖不同客户端、协议协商、取消、超时；仍保留单目录只读契约 |
| P2 | 大目录检索 | 先记录实际目录规模、延迟和漏扫率；再决定索引/缓存。缓存必须按授权目录隔离、跟踪文件变化并支持删除，不能跨用户复用敏感内容 |
| P2 | 可配置但默认收紧的排除规则 | 引入根目录配置与人工审核，测试正反例；模型不能自行修改读取边界 |
| P2 | 公共发布工程化 | 先选许可证，再建仓库/CI、跨平台矩阵和版本发布；建立来源/校验与安全反馈渠道 |

不建议给 Node 版追加写入/删除、多用户公开 HTTP 或自动全量上传。Python ZIP 已带本机审批流程，本轮保留但不在真实业务目录启用；它不是把 Node 只读契约改成了可写。后续共享解析器或协议适配必须先定义契约、迁移和回退，不能直接揉成一个服务。
