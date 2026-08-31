# 秋招工作台

一个通用的本地求职工作台。用 Markdown 与 CSV 管理从 JD 解析到投递追踪的完整链路，配合 AI CLI 驱动。

不是 SaaS，不联网，不上传任何数据。全部是纯文本文件，git 能 diff，Excel 能直接打开。

---

## 它解决什么问题

求职期的真实困难不是"不知道该怎么做"，而是**信息散落导致无法决策**：

- 这家公司值得投吗？上周看过类似的，当时怎么判断的？
- 三个月前投这家，用的是哪版简历？当时的 JD 怎么写的？
- 现在有几家在流程中？哪个明天截止？

工作台把这些变成可查询、可回溯的文件结构。

## 核心设计

**判断由 AI 做，脚本只做 IO 与校验。**

评分不是代码算出来的，是 AI 读 JD 原文与你的档案后填进解析卡的；Python 只校验加总自洽、套阈值出结论、生成 PDF、读写追踪表。改评分标准不用改代码，只改 `template/profiles/` 下的 Markdown。

**四层单向依赖**：skills（领域知识）→ 脚本（IO 与校验）→ 数据（Markdown + CSV）→ git（版本）。脚本互不调用，各自独立可测。

## 三层分离

```
工具层   tools/ + skills/      领域无关，任何人可用
领域层   template/profiles/    可插拔插件，内置 hvac-cooling
用户层   personal/             你的真实数据，从 template 初始化
```

新增一个领域只需新增一个插件目录，不改任何代码。

---

## 快速开始

```bash
# 1. 初始化工作区（一条命令生成六个模块 + 档案模板 + 领域插件）
python tools/init_workspace.py --target my_job_hunt --domain hvac-cooling

# 2. 分发 skills 到你的 AI CLI
python tools/install_skills.py --target user

# 3. 填写 my_job_hunt/AGENTS.md
#    第三节的硬门槛事实必填——不填则 JD 硬门槛判定会卡住（设计如此，不允许猜测）
```

然后直接用自然语言跟你的 AI CLI 说："解析这份 JD"、"投递这个岗位"、"看最近七天要处理什么"。

### 支持的 AI CLI

`tools/install_skills.py` 支持分发到 CodeBuddy（`.codebuddy/skills/`）、Claude Code（`.claude/skills/`）、以及跨运行时的用户级 `~/.agents/skills/`（Codex / Copilot CLI / Gemini CLI 共同识别）。

仓库内的 `skills/` 是单一源，改完重跑安装脚本即可同步到所有位置。

### 环境要求

- Python 3.8+（脚本只用标准库）
- pypdf（仅 PDF 校验需要）：`pip install pypdf`
- Chrome 或 Edge（仅 PDF 生成需要）

无 Python 环境也能用——skills 与数据层是纯 Markdown，只是五个脚本跑不了。

---

## 四个工作流

| 工作流 | 用途 |
|---|---|
| `jd` | 解析 JD：存原文 → 硬门槛过滤 → 四维度评分 → 出档位 |
| `apply` | 生成投递包：选简历版本 → 生成 PDF → ATS 校验 → 归档 → 记入追踪表 |
| `track` | 追踪表查改与漏斗看板 |
| `resume` | 单独重建 PDF 并校验 |

## 评分框架

Eligibility Gate 前置：**学历 → 专业 → 届数 → 外语 → 城市**，任一不过则不打分、不写材料。

通过后四维度加权：技术匹配 30、经历匹配 25、方向契合 30、培养与稳定性 15。

| 总分 | 档位 |
|---|---|
| 75–100 | 强烈建议投 |
| 60–74 | 建议投 |
| 45–59 | 斟酌 |
| 30–44 | 大概率跳过 |
| 0–29 | 不投 |

「培养与稳定性」取代了常见的「文化契合」——校招 JD 里的文化表述多为套话，判断可靠度低；而是否有培养体系、是否核心岗、工作形态是否可持续，既可从文本判断，也对决策影响更大。

## 五个脚本

```
python tools/init_workspace.py --target <名称> --domain <插件>
python tools/install_skills.py [--target user|codebuddy|claude|...] [--dry-run]
python tools/jd_score.py <解析卡> [--domain X --direction Y] [--show-profile]
python tools/tracker.py --workspace <目录> add|update|list|show
python tools/resume_build.py --workspace <目录> [--version X] [--out DIR]
python tools/report.py --workspace <目录> [--stdout]
```

---

## 领域插件

```
template/profiles/<domain-id>/
├── profile.md        插件元信息
├── lexicon.md        三级词典：Primary / Secondary / Weak
└── directions/
    └── <direction-id>.md
```

内置 `hvac-cooling`（暖通制冷与数据中心冷却），含 `datacenter` 与 `hvac` 两个方向。

**三级分层的判据不是"会不会"，是"能不能经得起追问"**：

- Primary —— 能讲清原理、能推导、能接两层追问
- Secondary —— 有实操，能支撑但要谨慎表述边界
- Weak —— 只有知识性了解，没有交付经历

把 Weak 写成 Primary 的代价远大于漏写：面试会露馅。

## 两条不可删除的红线

1. **简历每个动词都要经得起 5–10 分钟追问。** 动词由贡献事实决定，不把「参与」一律升级为「负责」。
2. **知识缺口用诚实的桥梁回答**，永不编造经历。

这两条对所有人都成立。此外你可以在 `AGENTS.md` 里定义自己的红线——通常是「哪些事不能认领」和「哪些数字必须怎么表述」。

## 目录

| 目录 | 用途 |
|---|---|
| `template/` | 通用骨架：档案模板、空工作区、领域插件 |
| `skills/` | 四个工作流 + recruit-coach 评分标准，跨运行时单一源 |
| `tools/` | 六个 Python 脚本 |
| `personal/` | 当前使用者的真实工作区（含姓名与照片，见下方警告） |
| `docs/specs/` | 设计文档 |

> **分享本仓库前请先移除 `personal/`**——它包含真实姓名、照片与联系方式。

## 相关文档

- **`docs/README.md`** —— 文档索引，含每份文档的状态（现行 / 已废弃）
- `template/AGENTS.example.md` —— 档案模板，含逐项填写说明
- `template/workspace/README.md` —— 六个模块的用途与填写要求
- `web/README.md` —— Web 界面启动与使用

设计文档（在 `docs/specs/`）：

| 文档 | 状态 |
|---|---|
| `2026-08-30-general-workbench-design.md` | 现行：通用工作台架构（三层分离、领域插件） |
| `2026-08-30-web-prototype-design.md` | 现行：Web 界面层（API 契约、并发与安全） |
| `2026-08-30-autumn-recruit-workbench-design.md` | ⚠️ 已废弃：v1.0 个人工具设计，目录结构已失效 |
