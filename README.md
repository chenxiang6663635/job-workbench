# 求职工作台

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

无 Python 环境也能用——skills 与数据层是纯 Markdown，只是六个脚本跑不了。

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

## 六个脚本

```
python tools/init_workspace.py --target <名称> --domain <插件>
python tools/install_skills.py [--target user|codebuddy|claude|...] [--dry-run]
python tools/jd_score.py <解析卡> [--domain X --direction Y] [--show-profile]
python tools/jd_score.py --gap --resume <版本> <解析卡>   # JD↔简历差距（可召回/真实缺口）
python tools/tracker.py --workspace <目录> add|update|list|show [--reason 原因]
python tools/tracker.py --workspace <目录> history [--id A001] [--limit N]
python tools/tracker.py --workspace <目录> interview add|list|show|update   # 面试记录
python tools/tracker.py --workspace <目录> contact add|list|show|update     # 招聘方联系人
python tools/tracker.py --workspace <目录> offer add|list|show|update       # Offer 事实
python tools/tracker.py --workspace <目录> import --file x.csv [--dry-run]  # CSV 批量导入（先预览差异）
python tools/tracker.py --workspace <目录> check                            # schema 自检
python tools/resume_build.py --workspace <目录> [--version X] [--out DIR]
python tools/resume_build.py render --workspace <目录> [--version X]  # 数据驱动标准版式
python tools/report.py --workspace <目录> [--stdout]   # 漏斗看板 + 周期复盘
```

> tracker 进入终态（已挂 / 已放弃 / 我拒绝的 offer）须填 `--reason`；终态不可回退、同公司+岗位自动去重。
> 每次字段变更（含面试与 offer）会入账 `05_投递追踪/history.csv`，`tracker.py history` 可查变更时间线。
> 「我拒绝的 offer」是双向选择不算失败，复盘归因里与「已挂/已放弃」分开统计。
> 面试 / 联系人 / Offer 是独立 CSV（外键关联追踪表），绝不加主表列——主表保持「一行一岗位」。

简历有两条路径：无子命令直接打手写 HTML（精排版式）；`render` 子命令由
`02_简历工坊/source/resume_<版本>.json` + 内置模板生成（标准版式，可复用、可在网页编辑）。

---

## 投递之后的闭环

投递只是开始。工作台把「投递后到入职之间」也纳入同一份数据：

- **面试记录**：每场的提问、回答、复盘入 `interviews.csv`——复盘是唯一能复利的部分；Web 一键导出 `.ics` 日程（提前 1 小时提醒）
- **招聘方联系人**：谁、聊到哪、下次何时跟进，超期自动琥珀提醒
- **Offer 对比**：多个 offer 的已知事实并排展示，**只并排、不推荐**——选择是你自己的
- **版本谱系**：哪版简历投了哪些岗位、各走到哪一步
- **周期复盘**：阶段转化率（从时间线重建，不是存量冒充）、停留中位天数、失败归因；「我拒绝的 offer」单独统计
- **失败原因聚类**：按 `config/failure_keywords.txt` 把失败归成几类，回答「到底败在哪一类」；样本少于 3 条时明确「样本太少，暂不展示」，不硬凑分类
- **面试题库**：面过的问题与自己的回答要点按公司归集，面试前先过一遍（Web「进展」页）
- **投递健康度**：紧急 / 逾期 / 停滞 / 正常四态，每条给出**具体理由**而非黑箱分数（Web 追踪表与看板）
- **数据安全**：全部写操作原子化（半成品文件不会出现）；一键快照备份到系统用户目录（工作区之外）；schema 自检发现坏文件自动隔离而非静默丢弃；整包导出随时可带走

详见 `docs/specs/2026-09-03-p0-p3-roadmap.md`。

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
| `personal/` | 使用者的真实工作区（**已整体 gitignore，仓库内不含任何真实数据**） |
| `docs/specs/` | 设计文档 |

> **隐私**：本仓库不含任何真实个人数据。`personal/` 是用你自己的真实数据（姓名、照片、联系方式、投递记录、事实卡）填充的工作区，
> 已整体排除在版本管理之外——克隆本仓库后它是空的，用 `python tools/init_workspace.py --target personal --domain <插件>` 生成你自己的。
> 也就是说：**你可以放心公开 fork，但不要把 `personal/` 里的内容贴进 issue、PR 或讨论区。**

## 相关文档

- **`docs/usage-guide.md`** —— 使用手册：启动、四页面详解、AI 工作流、CLI 速查、常见问题
- **`docs/README.md`** —— 文档索引，含每份文档的状态（现行 / 已废弃）
- **`CONTRIBUTING.md`** —— 开发流程规范：新需求四道门、分支策略、发布流程、可持续性约定
- **`CHANGELOG.md`** —— 变更记录
- `template/AGENTS.example.md` —— 档案模板，含逐项填写说明
- `template/workspace/README.md` —— 六个模块的用途与填写要求
- `web/README.md` —— Web 界面启动与使用

设计文档（在 `docs/specs/`）：

| 文档 | 状态 |
|---|---|
| `2026-08-30-general-workbench-design.md` | 现行：通用工作台架构（三层分离、领域插件） |
| `2026-08-30-web-prototype-design.md` | 现行：Web 界面层（API 契约、并发与安全） |
| `2026-08-31-job-workbench-productization.md` | 现行：产品化路线（差异化点、workspace/BYOK、Electron、PyInstaller 打包） |
| `2026-08-30-autumn-recruit-workbench-design.md` | ⚠️ 已废弃：v1.0 个人工具设计，目录结构已失效 |
