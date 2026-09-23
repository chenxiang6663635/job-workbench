# 术语表

CHANGELOG 与各文档里出现的**内部术语**集中在这里定义一次；正文里再遇到，直接回查本表。

| 术语 | 含义 | 出处 / 延伸 |
|---|---|---|
| **两段式（写入）** | 任何写入先出「预览 + 差异 + 令牌」，确认后再凭令牌落盘——全站唯一写通道 | CONTRIBUTING、`docs/four-ends.md` |
| **令牌** | 两段式第一步签发的一次性凭据：绑定工作区、带载荷指纹、10 分钟有效、用完即焚 | `mcp/README.md`、CONTRIBUTING |
| **托管语义** | 镜像/同步时，目标目录视为「被托管」：源里删了它就删、源里改了它就改 | 使用手册「导成 Obsidian 笔记」 |
| **白名单（同步）** | `--sync-to` 只碰的顶层条目集合（八张表目录 / `README.md` / `jobws.base` / 材料目录），集合外零接触 | 使用手册、四端矩阵 |
| **四端矩阵** | CLI / AI 宿主 / 编辑器插件 / 桌面界面四端的能力与错误码对照；真值源 `tools/four_ends_matrix.json` | `docs/four-ends.md` |
| **硬闸（闸门）** | 不满足条件就拒绝继续的检查点（如 CI 门禁、历史上 MCP 的「仓库在侧」硬闸） | CHANGELOG |
| **壳层** | MCP 服务的外层：把协议调用翻译成领域层调用、并补协议级用例的那一层 | CHANGELOG、`mcp/` |
| **shim（转发层）** | 旧 import 名的兼容文件：只做 `sys.modules` 转发 + 废弃告警，让旧路径平滑迁移 | CONTRIBUTING、CHANGELOG |
| **领域层包化** | 把领域模块搬进 `packages/jobws-core` 独立安装包（`jobws_core`），仓库侧只留转发 | 包 README、CHANGELOG |
| **旧名水位** | 旧 import 名剩余数量的清单上限：只许下降，降到 0 就删 shim | `tools/legacy_imports_allowlist.txt` |
| **规模水位线** | 超规模文件登记的行数上限：只许变小；降到阈值以内时要求删条目（自洁） | `tools/size_allowlist.txt`、CONTRIBUTING |
| **自洁强制** | 水位降到阈值以内时，检查器报错要求删掉登记条目——防止清单腐化 | CONTRIBUTING「规模预算」 |
| **单一发布节点** | 中间批次不 bump / 不 tag / 不 Release；全部批次做完后只发布一次 | CONTRIBUTING「版本号体系」 |
| **发布号 / 机器版本** | 发布号 `YY.MM.DD.N`（tag 与 CHANGELOG 段名）；机器版本 `YY.M.D`（`package.json` 与界面「关于」显示） | CONTRIBUTING「版本号体系」 |
| **指纹** | 三类：载荷指纹（令牌绑定载荷）、行指纹（删除落盘前复核那一行）、工作区指纹（界面 10 秒感知外部改动） | 使用手册、CHANGELOG |
| **应用根 / 数据根 / 允许根** | 路径解析的三个位置概念：模板所在（应用根）、可写数据所在（数据根）、允许访问的根集合（允许根） | CHANGELOG、`jobws_core.pathres` |
| **静默吞错** | `except: pass` / 空 `catch {}` 一类「出错无声」的写法——仓库禁用它，至少记日志 | CONTRIBUTING「代码卫生」 |
| **跨层测试** | 覆盖多层协作（如 CLI → 领域层 → 文件）的测试；打桩对象应是包内实现而不是转发层 | CHANGELOG、`tests/` |
| **打桩** | 测试里替换依赖对象以隔离被测范围（例如替换 `approval._shell`） | CHANGELOG、`tests/` |
| **PEP 562 门面** | 模块级 `__getattr__`，让「包当单文件」的旧 import 语义继续成立 | CHANGELOG |
| **拍板** | 需要用户明确确认的决策点；未拍板不做 | CHANGELOG.md、代码注释 |
| **截断诚实** | 内容被截断时必须显式告知（如 256 KB 截断并提示），不许静默少给 | 使用手册、CONTRIBUTING |
| **四道门** | 新需求准入的四步评估流程，见 CONTRIBUTING | CONTRIBUTING |
| **宿主提示缓存** | MCP 宿主会缓存工具清单——新工具一律**追加在注册末尾**，避免作废缓存 | CHANGELOG、`mcp/` |
| **批次（PR-A / PR-B / 批 4.6 / 批 8 / 收尾批）** | 内部计划里的工作批次编号，用于指代某一段工程；细节看 CHANGELOG 对应条目 | CHANGELOG |
| **候选池** | `ROADMAP.md` 里「想过但决定现在不做」的暂缓事项登记处：每条写一句话 + **触发条件**，开工前先走四道门 | `ROADMAP.md` |
| **毕业条件** | 首个时间戳发布等于 1.0-equivalent 的**可核判据**（连续自用无阻断、主流程冒烟、无未决阻断项、兼容条款生效） | `docs/support-and-compatibility.md` |
| **ADR（决策记录）** | 一条一文件的短决策记录（背景 / 决策 / 已评估的替代方案 / 复评条件），放 `docs/decisions/`；回答「为什么这样定」，路线图只回答「做什么」 | `docs/decisions/`、`docs/README.md` |
| **过渡纪律（Deprecated → Removed）** | 破坏性变更先废弃、保持读时兼容，至少一个发布节点后才移除，并在 CHANGELOG 显式列出（即使升级无需动作） | `CHANGELOG.md`、`docs/support-and-compatibility.md` |
| **冒烟** | 最小可运行的端到端验证（打包后真跑一遍），与单元测试互补 | CONTRIBUTING |
