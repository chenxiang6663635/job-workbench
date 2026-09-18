# 求职工作台 · AI 约定

本文件是 AI 在本仓库工作的约定入口（CodeBuddy / Claude Code / Codex / Gemini CLI 都会读取）。

## 仓库定位

这是一个**通用求职工作台**，不是某个人的求职资料库。三层分离：

```
工具层   tools/ + skills/      领域无关
领域层   template/profiles/    可插拔插件
用户层   personal/             某个使用者的真实数据
```

**改动工具层时必须保持领域无关。** 涉及具体领域知识的改动应放进插件，涉及具体个人事实的应放进 `personal/`。

## 四个入口（同一件事在哪端叫什么）

同一个能力在四个入口都能用，**说法与确认方式对齐**是硬要求：

| 入口 | 形态 | 写入口令 |
|---|---|---|
| 命令行 | `tools/jobws.py`（唯一入口） | `--preview` 拿令牌 → `jobws apply <令牌>` |
| AI 宿主 | MCP 服务（`mcp/jobws_mcp`） | `preview_*` 拿令牌 → `apply_approval` |
| 编辑器插件 | 仓库根 `commands/` 与 `agents/` | 命令内仍走命令行的两段式 |
| 桌面端 | `web/backend/routers` + 前端页面 | 界面弹窗确认 |

- **能力对照表**在 `docs/four-ends.md`（由 `tools/four_ends_matrix.json` 生成，**不要手改**）；
  "哪端不提供某项能力、为什么"也记在那里。
- **新增能力要三处一起改**：实现（领域层）→ 矩阵登记（`tools/four_ends_matrix.json`）
  → 重新生成说明页（`python tools/jobws.py lint four-ends --write`）。
  漏了会被 `python tools/jobws.py lint four-ends` 拦下（CI 同一实现）。
- 技能资产分发到各宿主（`.claude` / `.agents` / `.codex` / `.codebuddy`）用
  `python tools/jobws.py skills install`；镜像与真源不一致同样会被上面那个检查器报出来。
- MCP 怎么接进宿主见 `docs/mcp-integration.md`——**配置键名按宿主不同，别照抄**。

## 执行任何任务前

- 操作用户数据时，先读工作区的 `AGENTS.md`（默认 `personal/AGENTS.md`）——档案、硬门槛事实、自定义红线
- 评分标准与流程见 `skills/jwb-recruit-coach/SKILL.md`
- 硬门槛事实为 `[待填]` 时按 **fail** 处理并提示补齐，禁止猜测

## 两条通用诚实红线

1. 简历每个动词都要经得起 5–10 分钟追问；不把「参与」一律升级为「负责」
2. 知识缺口用诚实的桥梁回答，永不编造经历

用户自定义的红线在其工作区 `AGENTS.md` 中，执行时必须一并遵守。

## 工程约束

- **Python 3.12 基线**（2026-09-14 从 3.8 升上来）：脚本可以用现代语法（`dict | dict`、`list[str]` 等）；CI 与打包都跑 3.12，`imaplib` 的超时直接用 `IMAP4_SSL(timeout=…)`
- 脚本只用标准库；pypdf 仅用于 PDF 校验
- 所有脚本接受 `--workspace`，默认 `personal/`；不得硬编码具体工作区路径
- `tools/` 是**分层包**：统一入口 `jobws.py` + 领域模块 + 门禁脚本；模块间依赖须**无环**（领域层不 import Web/协议层；跨模块协作在函数内惰性 import 破环），各自独立可测
- CSV 一律 `utf-8-sig` 读写，保证 Excel 打开中文不乱码
- **新需求优先改成 skills 里的工作流步骤**，只有"必须可复现、可批量重算、或涉及二进制处理"才新增模块；新模块按三层归位（入口 / 领域 / 门禁）并在文件头写明职责——`tools/` 已从早期的六个脚本生长为分层包，**增殖仍要克制**
- **不得自动 `git commit`**——生成提交信息交用户确认后再提交
- **隐私约定**：工作区 `personal/` 含真实数据且已整体 gitignore（历史已清洗），**禁止提交或外泄其内容**；细则见 `CONTRIBUTING.md` 隐私约定节
- **验证链**：`python -m pytest tests/ -q`（护栏 + 健康度）全绿 + 前端 `npm run build`；push / PR 由 GitHub Actions 跑同款门禁
- **Web 层铁律**：后端直接复用 `tools/` 函数并显式传 `workspace`（模块级全局并发下会互相覆盖）；写操作持 `filelock`；路径过 `safe_join`；不加缓存

## 目录约定

| 目录 | 约定 |
|---|---|
| `00_事实库/` | 唯一事实源。简历动词、行为故事、经历匹配打分都必须回查，不得以解析卡概述为准 |
| `01_岗位池/` | 每个岗位一目录，保留 JD 原文不改写 |
| `02_简历工坊/` | PDF 生成源是 HTML 不是 Markdown，改简历必须同步改 HTML |
| `03_面试准备/` | 表达训练材料。先有表达，再补知识 |
| `04_知识库/` | 按需查阅，日常训练不从这里开始 |
| `05_投递追踪/` | `tracker.csv` + 每次投递归档 |
| `99_归档/` | 历史文件只增不改。其中的旧目录名不做改写——如实记录当时状态才是其价值 |

## 新增领域

在 `template/profiles/` 下新建 `<domain-id>/`，含 `profile.md`、`lexicon.md`、`failure_keywords.txt`、`directions/*.md`。无需改动任何 Python 代码——脚本按 ID 查找目录。**契约与校验**：全文见 `docs/domain-contract.md`；提交前跑 `python tools/jobws.py lint domains`（CI 同一实现）。
