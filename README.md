# 求职工作台

[![CI](https://github.com/chenxiang6663635/job-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/chenxiang6663635/job-workbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)

一个通用的本地求职工作台：用 Markdown 与 CSV 管理从 JD 解析到投递追踪的完整链路，配合你的 AI CLI 驱动。

本地优先：数据全部留在你自己的磁盘上，默认离线可用（BYOK 模型调用与 JD 链接抓取是可选联网功能，key 与数据只存本地）。全部是纯文本文件，git 能 diff，Excel 能直接打开。

## 它解决什么问题

求职期的真实困难不是"不知道该怎么做"，而是**信息散落导致无法决策**：

- 这家公司值得投吗？上周看过类似的，当时怎么判断的？
- 三个月前投这家，用的是哪版简历？当时的 JD 怎么写的？
- 现在有几家在流程中？哪个明天截止？

工作台把这些变成可查询、可回溯的文件结构。

## 核心设计

- **评分判断由 AI 做，确定性判定由脚本做**。岗位评分是 AI 读 JD 原文与你的档案后填进解析卡的；Python 只校验加总自洽、套阈值出结论、生成 PDF、读写追踪表，以及做可解释的确定性判定（健康度四态、CSV 导入差异、失败聚类——全部给理由）。改评分标准不用改代码，只改 `template/profiles/` 下的 Markdown
- **四层单向依赖**：skills（领域知识）→ 脚本（IO 与校验）→ 数据（Markdown + CSV）→ git（版本）。脚本互不调用（例外：`report.py` 复用 `tracker.py` 的读写函数），各自独立可测
- **三层分离**：工具层 `tools/` + `skills/`（领域无关）· 领域层 `template/profiles/`（可插拔插件，内置 hvac-cooling）· 用户层 `personal/`（你的真实数据，从 template 初始化）。三级词典的判据是"能不能经得起追问"而非"会不会"，见 [`template/AGENTS.example.md`](template/AGENTS.example.md)

## 功能一览

- **四个 CLI 工作流**：`jd`（JD 解析评分）、`apply`（投递包）、`track`（追踪看板）、`resume`（PDF 重建校验）——六个脚本的全部命令见[使用手册 CLI 命令速查](docs/usage-guide.md)
- **Web 界面**（`web/`）：七个页面与 CLI 共享同一份数据——看板、追踪表、简历工坊（一键导入**抽取而非生成** + AI 改写反编造护栏 + 导出 Word）、进展（面试题库）、复盘等，详见 [`web/README.md`](web/README.md)
- **投递之后的闭环**：面试记录（Web 一键导出 .ics 日程）、招聘方联系人跟进提醒、Offer 并排对比（只并排、不推荐）、版本谱系、周期复盘（阶段转化率从时间线重建）、失败原因聚类、投递健康度四态（每条给具体理由而非黑箱分数）
- **评分框架**：Eligibility Gate 前置（学历 → 专业 → 届数 → 外语 → 城市，任一不过不打分不写材料），通过后四维度加权、五档位结论，完整标准见 [`skills/recruit-coach/SKILL.md`](skills/recruit-coach/SKILL.md)

## 快速开始

```bash
# 1. 初始化工作区（一条命令生成六个模块 + 档案模板 + 领域插件）
python tools/init_workspace.py --target my_job_hunt --domain hvac-cooling

# 2. 分发 skills 到你的 AI CLI（CodeBuddy / Claude Code / 跨运行时 ~/.agents/skills/）
python tools/install_skills.py --target user

# 3. 填写 my_job_hunt/AGENTS.md
#    第三节的硬门槛事实必填——不填则 JD 硬门槛判定会卡住（设计如此，不允许猜测）
#    文件里还有两条通用诚实红线：简历动词经得起追问、永不编造经历
```

然后直接用自然语言跟你的 AI CLI 说："解析这份 JD"、"投递这个岗位"、"看最近七天要处理什么"。

环境要求：Python 3.8+（脚本只用标准库）；pypdf 仅 PDF 校验需要；Chrome 或 Edge 仅 PDF 生成需要；Web 界面（可选）见 [`web/README.md`](web/README.md)。

## 隐私

本仓库不含任何真实个人数据。`personal/` 是用你自己的真实数据（姓名、照片、联系方式、投递记录、事实卡）填充的工作区，已整体排除在版本管理之外——克隆本仓库后它是空的，用上面的初始化命令生成你自己的。也就是说：**可以放心公开 fork，但不要把 `personal/` 里的内容贴进 issue、PR 或讨论区。**

## 目录

| 目录 | 用途 |
|---|---|
| `template/` | 通用骨架：档案模板、空工作区、领域插件 |
| `skills/` | 四个工作流 + recruit-coach 评分标准，跨运行时单一源 |
| `tools/` | 六个 Python 脚本 |
| `web/` | Web 界面：FastAPI 后端 + React 前端（七个页面），与 CLI 共享同一份数据 |
| `tests/` | 33 项测试（反编造护栏 + 健康度语义），CI 质量门 |
| `personal/` | 使用者的真实工作区（**已整体 gitignore，仓库内不含任何真实数据**） |
| `docs/` | 使用手册、文档索引、设计文档（`docs/specs/`） |
| `.github/` | CI 工作流、issue / PR 模板、行为准则、Copilot 指引 |

## 文档

- [文档索引](docs/README.md)——每份文档的状态（现行 / 已废弃）
- [使用手册](docs/usage-guide.md)——启动、七页面详解、AI 工作流、CLI 命令速查、常见问题
- [设计文档](docs/specs/)——架构、Web 契约、产品化路线、开源发布
- [变更记录](CHANGELOG.md)

## 贡献

欢迎 issue 与 PR。提交前请读 [CONTRIBUTING.md](CONTRIBUTING.md)（新需求四道门、分支策略、发布流程），遵守[行为准则](.github/CODE_OF_CONDUCT.md)；本地先跑 `pip install -r web/backend/requirements-dev.txt && python -m pytest tests/ -q`（33 项基线）与前端 `npm run build`。

## License

[MIT](LICENSE) © job-workbench contributors，第三方依赖许可见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
