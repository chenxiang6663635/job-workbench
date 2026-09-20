# 四端能力对照（自动生成，不要手改）

> 真源是 `tools/four_ends_matrix.json`；本文件由 `python tools/jobws.py lint four-ends --write` 生成，
> 并由同一个检查器校验是否同步。

四端：**命令行**（`tools/jobws.py`）/ **AI 宿主**（MCP 服务）/ **编辑器插件**（`commands/` 与 `agents/`）/ **桌面端**（后端接口与界面）。

写入类能力一律「预览 → 确认 → 落盘」：命令行与 AI 宿主凭令牌，界面靠弹窗确认——机制不同、语义相同。

## 能力矩阵

| 阶段 | 能力 | 命令行 | AI 宿主（MCP） | 插件 | 桌面端 |
|---|---|---|---|---|---|
| JD 解析 | `jd.score` | `jd` | `score_jd` | `jd` | `GET /api/jobs/{job_id}/gap` |
| JD 解析 | `jd.fetch` | — | — | — | `POST /api/jobs/fetch-jd` |
| 岗位池 | `job.list` | — | `list_jobs` | `resume-jd-gap` | `GET /api/jobs` |
| 岗位池 | `job.create` | — | — | — | `POST /api/jobs` |
| 投递 | `application.list` | `track list` | `list_applications` | `today` | `GET /api/applications` |
| 投递 | `application.add` | `track add` | `preview_add_application` | `apply-pack` | `POST /api/applications` |
| 投递 | `application.update` | `track update` | `preview_update_application` | — | `PATCH /api/applications/{app_id}` |
| 投递 | `application.import` | `track import` | `preview_import_applications` | — | `POST /api/applications/import` |
| 投递 | `application.history` | `track history` | — | — | `GET /api/applications/{app_id}/history` |
| 投递 | `application.check` | `track check` | — | — | — |
| 跟进 | `mail.record` | `track mail` | — | — | `POST /api/progress/mails` |
| 跟进 | `imap.fetch` | — | — | — | `POST /api/imap/fetch` |
| 跟进 | `contact.record` | `track contact` | — | — | `POST /api/progress/contacts` |
| 跟进 | `talk.record` | `track talk` | — | — | `POST /api/progress/talks` |
| 跟进 | `offer.record` | `track offer` | — | — | `POST /api/progress/offers` |
| 面试 | `interview.list` | `track interview` | `list_interviews` | `retro` | `GET /api/progress/interviews` |
| 面试 | `interview.add` | `track interview` | `preview_add_interview` | — | `POST /api/progress/interviews` |
| 面试 | `interview.update` | `track interview` | `preview_update_interview` | — | `PATCH /api/progress/interviews/{interview_id}` |
| 复盘 | `report.summary` | `report` | `dashboard_summary` | `today` | `GET /api/dashboard` |
| 题库 | `question.list` | `bank list` | `list_questions` | `bank` | `GET /api/progress/questions` |
| 题库 | `question.add` | `bank add` | `preview_add_question` | `bank` | — |
| 题库 | `question.update` | `bank update` | — | — | `GET /api/progress/questions/preview-update` |
| 题库 | `question.import` | `bank import` | `preview_import_questions` | `bank` | `GET /api/progress/questions/preview-import` |
| 通用 | `approval.apply` | `apply` | `apply_approval` | — | `POST /api/approvals/apply` |
| 笔记 | `prep.toggle` | — | — | — | `GET /api/prep/{section}/preview-toggle` |
| 通用 | `export.obsidian` | `export --obsidian` | — | — | — |
| 题库 | `question.due` | `bank due` | — | — | — |

## 各端不提供的能力（含原因）

- **cli** · `prep.toggle`：打勾是界面里的学习打卡动作；命令行侧直接编辑 Markdown 即可，不代劳。
- **mcp** · `prep.toggle`：学习进度由本人维护——勾选不由模型代劳。
- **plugin** · `prep.toggle`：同上：勾选项是本人的学习打卡动作。
- **mcp** · `export.obsidian`：导出是本地文件动作（往用户指定的目录写一批 md），不由模型代劳。
- **plugin** · `export.obsidian`：同上：导出到本地笔记库是本人发起的动作。
- **gui** · `export.obsidian`：界面的导出是「整包 zip」（设置页，保留 CSV 原格式）；Obsidian 笔记形态只在命令行提供——形态不同，不是漏做。
- **mcp** · `question.due`：复习清单是本人的每日动作，模型不代劳；需要时让用户跑 `jobws bank due`。
- **plugin** · `question.due`：同上。
- **gui** · `question.due`：界面侧的复习入口（今日待复习 + 错题本）随复习面一并设计，本批只上 CLI。
- **cli** · `job.list`：岗位池以解析卡路径为输入（jd 命令），没有独立的列表命令；GUI 与 MCP 侧有。
- **cli** · `jd.fetch`：抓取需在界面粘贴链接；命令行侧由使用者自行取文本。
- **cli** · `imap.fetch`：邮箱凭证配在 GUI 设置里，命令行侧不重复实现。
- **mcp** · `jd.fetch`：抓取涉及出网与页面解析，不由模型代劳；模型应让用户提供 JD 文本。
- **mcp** · `job.create`：岗位新建属界面动作（需粘贴 JD 或链接），不由模型代劳。
- **mcp** · `application.history`：时间线可由 list 结果推断；工具数需收敛，暂不单开。
- **mcp** · `application.check`：schema 自检属运维动作，由 CLI 执行。
- **mcp** · `mail.record`：写入面暂收敛到投递与面试；邮件台账由 GUI 或 CLI 记录。
- **mcp** · `imap.fetch`：出网拉取邮箱不由模型代劳（凭证与网络都属用户环境）。
- **mcp** · `contact.record`：写入面暂收敛；联系人由 GUI 或 CLI 记录。
- **mcp** · `talk.record`：写入面暂收敛；宣讲会由 GUI 或 CLI 记录。
- **mcp** · `offer.record`：写入面暂收敛；Offer 由 GUI 或 CLI 记录。
- **mcp** · `question.update`：做题状态与难度由本人维护，模型只负责新增与导入。
- **plugin** · `job.create`：需要界面粘贴 JD，命令不代劳。
- **plugin** · `jd.fetch`：同上。
- **plugin** · `imap.fetch`：邮箱凭证与出网动作不放进命令。
- **plugin** · `application.update`：命令侧暂不提供单条更新（走 apply-pack 的完整流程或用 CLI）。
- **plugin** · `application.import`：CSV 批量导入是界面动作。
- **plugin** · `application.history`：时间线可由 track list 与 report 覆盖。
- **plugin** · `application.check`：运维动作，由 CLI 执行。
- **plugin** · `mail.record`：邮件台账由 GUI 记录。
- **plugin** · `contact.record`：联系人由 GUI 记录。
- **plugin** · `talk.record`：宣讲会由 GUI 记录。
- **plugin** · `offer.record`：Offer 由 GUI 记录。
- **plugin** · `interview.add`：面试记录由 retro 只读汇总；写入走 CLI 或 GUI。
- **plugin** · `interview.update`：同上。
- **plugin** · `question.update`：做题状态由本人维护。
- **gui** · `question.add`：界面暂无单题新增入口（走批量导入，或命令行 bank add）——改已有题的入口已在详情弹窗里提供。
- **gui** · `application.check`：schema 自检是命令行运维动作，不在界面暴露。
- **gui** · `jd.score`：界面只展示差距（gap），评分由解析卡承载；命令行 jd 是完整的评分校验入口。

## 错误标识对照

| 错误标识 | 后端错误码 | 界面文案键 | 命令行退出码 |
|---|---|---|---|
| `approval.bad_token` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.not_found` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.expired` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.binding` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.fingerprint` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.unreadable` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.lost` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.unknown_operation` | `approval.tokenInvalid` | `err.approval.tokenInvalid` | 1 |
| `approval.conflict` | `approval.conflict` | `err.approval.conflict` | 1 |

## 宿主专属字段

| 文件 | 字段 | 生效宿主 | 说明 |
|---|---|---|---|
| `agents/*.md` | `agentMode` | codebuddy | 取值 agentic / readonly；其他宿主不识别此字段，失效时静默——不影响 tools 白名单的约束。 |
| `agents/*.md` | `enabled` | codebuddy | 宿主侧开关；其他宿主忽略。 |
| `agents/*.md` | `enabledAutoRun` | codebuddy | 宿主侧自动运行开关；其他宿主忽略。 |
| `agents/*.md` | `tools` | any | 工具白名单，跨宿主通用（Claude Code 同名同义）；只给只读工具。 |
| `commands/*.md` | `description` | any | 命令列表展示文案，跨宿主通用。 |
| `commands/*.md` | `allowed-tools` | codebuddy | 权限白名单。Claude Code 的命令 frontmatter 亦用同名键，但取值语法可能不同（未实证）——新增命令时以本机宿主实测为准。 |
| `skills/*/SKILL.md` | `compatibility` | any | 环境声明（Python 版本、是否需仓库在侧、是否上传数据）；宿主据此判断能否挂载。 |
