[English](README.md) | 简体中文

# 求职工作台

[![CI](https://github.com/chenxiang6663635/job-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/chenxiang6663635/job-workbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)

一个**本地优先、AI 可审计**的求职工作台：从 JD 解析到 offer 决策的完整链路，用纯 Markdown 与 CSV 管理在你自己的磁盘上，由你自己的 AI CLI 驱动。

## 为什么做这个项目

求职意味着敏感的个人数据（简历、电话、投递历史）——以及可能悄悄编造事实的 AI 输出。这个项目围绕三个回答构建：

- **本地优先的隐私**。一切以纯文本存在你自己的磁盘上——git 能 diff、Excel 能打开、无遥测、无服务器。真实个人数据留在 `personal/`（整体 gitignore）：克隆本仓库得到空工作区，你可以放心公开 fork 而不泄露任何东西。
- **可审计的 AI，而非黑箱自动化**。你自己的 AI CLI（BYOK 模型）做语义判断——读 JD、评匹配度；Python 脚本做一切确定性的事：资格门槛、评分校验、PDF 生成、追踪表读写——且每个自动判定（投递健康度、CSV 导入差异、失败聚类）都附带明确的、可人工核对的**理由**，绝不是一个裸分数。
- **反编造护栏**。简历导入是**抽取而非生成**：每个落盘的值都必须能在原文找到，未抽到的字段标黄。AI 改写建议必须通过五项本地反编造校验才能被采用。

## 它解决什么问题

求职期的真实困难不是「不知道该怎么做」，而是**信息散落导致无法决策**：

- 这家公司值得投吗？上周看过类似的，当时怎么判断的？
- 三个月前投这家，用的是哪版简历？当时的 JD 怎么写的？
- 现在有几家在流程中？哪个明天截止？

工作台把这些变成可查询、可回溯的文件结构。

## 核心设计

- **AI 判断，脚本校验**。评分由 AI 读 JD 与你的档案后填进解析卡；Python 只校验加总自洽、套阈值出结论、生成 PDF、读写追踪表，并做可解释的确定性判定（健康度四态、CSV 导入差异、失败聚类——全部给理由）。改评分标准只改 Markdown 配置，不改代码。
- **四层单向依赖**：skills（领域知识）→ 脚本（IO 与校验）→ 数据（Markdown + CSV）→ git（版本）。脚本互不调用（例外：`report.py` 复用 `tracker.py` 的读写），各自独立可测。
- **三层分离**：工具层（`tools/` + `skills/`，领域无关）· 领域层（`template/profiles/`，可插拔）· 用户层（`personal/`，你的真实数据）。三级词典的判据是「能不能经得起追问」而非「会不会」，见 [`template/AGENTS.example.md`](template/AGENTS.example.md)。

## 功能一览

- **四个 CLI 工作流**：`jwb-jd`（JD 解析评分）、`jwb-apply`（投递包）、`jwb-track`（追踪看板）、`jwb-resume`（PDF 重建校验）——六个脚本的全部命令见[使用手册 CLI 命令速查](docs/usage-guide.zh-CN.md)
- **Web 界面**（`web/`）：七个页面与 CLI 共享同一份数据——看板、追踪表、简历工坊（一键导入**抽取而非生成** + AI 改写反编造护栏 + 导出 Word）、进展（面试题库）、复盘等，详见 [`web/README.md`](web/README.md)
- **投递之后的闭环**：面试记录（一键导出 .ics）、招聘方联系人跟进提醒、Offer 并排对比（**只并排事实，绝不给建议**）、版本谱系、周期复盘、失败聚类、投递健康度四态——每条给具体理由而非黑箱分数
- **只读邮箱拉取（可选）**：用你自己的 IMAP 授权码拉取最近的招聘邮件，转成逐条状态建议；只读连接、只在点击时连接、凭证只存本地、确认前不改数据——详见[使用手册](docs/usage-guide.zh-CN.md)
- **评分框架**：资格门槛前置（学历 → 专业 → 届数 → 外语 → 城市，任一不过不打分），四维度加权五档位，完整标准见 [`skills/jwb-recruit-coach/SKILL.md`](skills/jwb-recruit-coach/SKILL.md)

## 界面预览

界面**中英双语**：每一页都有中文与英文，顶栏的 `中文 / English` 可随时切换（首次按系统语言，选择会被记住）。下面截图是中文界面（英文的那套在 [README.md](README.md) 同一节，两套取自同一个 demo 工作区）；英文界面是同样页面换了界面文字。仍然保留中文的只有三处：你自己录进工作区的内容、CSV / Markdown 里存的枚举取值（与 CLI 共享的数据契约）、CLI 自带帮助——都有意为之。

以下页面全部由 demo 数据生成（`init_workspace.py --target demo --demo`），公司、岗位、人名均为占位（`示例科技`、`示例同学` 等），不含任何真实信息。

![看板](docs/screenshots/zh-CN/01-dashboard.png)
![追踪表](docs/screenshots/zh-CN/02-applications.png)
![岗位池](docs/screenshots/zh-CN/03-jobs.png)
![简历工坊](docs/screenshots/zh-CN/04-resume.png)
![进展](docs/screenshots/zh-CN/05-progress.png)
![素材库](docs/screenshots/zh-CN/06-library.png)
![设置](docs/screenshots/zh-CN/07-settings.png)

## 快速开始

不想配环境的话，[Releases](https://github.com/chenxiang6663635/job-workbench/releases/latest) 里有桌面版 `job-workbench-setup-*.exe`（免 Python / Node）：安装包是**向导式**——可自选安装位置，并选择「为所有用户 / 仅为我」（升级旧版时沿默认选项即可）。数据在 `%APPDATA%\job-workbench\`，不离开本机。

```bash
# 1. 初始化工作区（生成六个模块 + 档案模板 + 领域插件）
python tools/jobws.py init --target my_job_hunt --domain software-backend

# 2. 分发 skills 到你的 AI CLI（CodeBuddy / Claude Code / 跨运行时 ~/.agents/skills/）
python tools/jobws.py skills install --target user

# 3. 填写 my_job_hunt/AGENTS.md
#    第三节的硬门槛事实必填——不填则 JD 硬门槛判定会卡住（设计如此，不允许猜测）
#    文件里还有两条通用诚实红线：简历动词经得起追问、永不编造经历
```

**用 CodeBuddy？** 同一套技能也打包为 CodeBuddy 插件——把本仓库加为插件市场并安装即可（插件直接读 `skills/`，没有第二份副本）：

```
/plugin marketplace add https://github.com/chenxiang6663635/job-workbench
/plugin install job-workbench
```

然后直接用自然语言跟你的 AI CLI 说："解析这份 JD"、"投递这个岗位"、"看最近七天要处理什么"。

环境要求——命令行：Python 3.8+（只用标准库）；pypdf 仅 PDF 校验需要；certifi 提供出网证书兜底（系统证书库不可用时回退到随包 CA 清单，HTTPS / IMAP 共用）。PDF 生成：Chrome 或 Edge。Web 界面（可选）见 [`web/README.md`](web/README.md)。

## 推广说明

AI 功能是 BYOK：自带任意 OpenAI 兼容服务商的 key 即可。还没有 key 的话，设置页把 [OrcaRouter](https://www.orcarouter.ai/ref/ref_f34ad879f774bce8bc82) 预置为可选 Provider。如实说明：这是一个**推广（返佣）链接**——通过它注册会给本项目作者返佣；你的价格与权益不受影响，点击也只是打开网页（本应用不会因点击发出任何数据）。

## 隐私

本仓库**不含任何真实个人数据**。`personal/` 是用你自己的真实数据（姓名、照片、联系方式、投递记录、事实卡）填充的工作区，已整体排除在版本管理之外——克隆本仓库后它是空的，用上面的初始化命令生成你自己的。也就是说：**可以放心公开 fork，但不要把 `personal/` 里的内容贴进 issue、PR 或讨论区。**

## 目录

| 目录 | 用途 |
|---|---|
| `template/` | 通用骨架：档案模板、空工作区、领域插件 |
| `skills/` | 四个求职向工作流 + 教练评分标准，另有三个开发向技能（CLI 契约 / API 审查 / MCP），跨运行时单一源 |
| `tools/` | 六个 Python 脚本 |
| `web/` | Web 界面：FastAPI 后端 + React 前端（七个页面），与 CLI 共享同一份数据 |
| `tests/` | pytest 测试套件（隐私护栏、反编造检查、追踪表语义），CI 质量门 |
| `personal/` | 使用者的真实工作区（**已整体 gitignore，仓库内不含任何真实数据**） |
| `docs/` | 使用手册、文档索引、设计文档（`docs/specs/`） |
| `.github/` | CI 工作流、issue / PR 模板、行为准则、Copilot 指引 |
| `.codebuddy-plugin/` | CodeBuddy 插件清单——把同一份 `skills/` 交给插件系统，不另存副本 |

## 文档

- [Roadmap](ROADMAP.md)——Now / Next / Later，每项都链接到跟踪 issue
- [文档索引](docs/README.md)——每份文档的状态（现行 / 已废弃）
- [使用手册](docs/usage-guide.zh-CN.md)——启动、七页面详解、AI 工作流、CLI 命令速查、常见问题（英文主版：[usage-guide.md](docs/usage-guide.md)）
- [设计文档](docs/specs/)——架构、Web 契约、产品化路线、开源发布
- [变更记录](CHANGELOG.md)

## 贡献

欢迎 issue 与 PR——bug 修复、文档、新领域插件、隐私护栏、测试与互操作性改进尤其有用。请先读 [CONTRIBUTING.md](CONTRIBUTING.md)（新需求四道门、分支策略、发布流程）与[行为准则](.github/CODE_OF_CONDUCT.md)；**安全漏洞请走私密通道，见 [SECURITY.md](SECURITY.md)**（不要开公开 issue）；代码改动走 PR（CI 绿：后端测试 + 前端构建），纯文档可直推。

## License

[MIT](LICENSE) © job-workbench contributors，第三方依赖许可见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
