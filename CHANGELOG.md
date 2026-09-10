# Changelog

本项目的所有显著变更记录于此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（0.x 阶段简化规则见 [CONTRIBUTING.md](CONTRIBUTING.md)）。

**版本号唯一来源**：`web/electron/package.json` 的 `version` 字段。
**tag 约定**：每个版本发布时打 `v<版本号>` tag（首个为 `v0.1.0`，2026-09-08）。

**取材原则**：只记录对使用者可见的软件变更（功能 / 修复 / 破坏性变更）。向工作区录入个人数据（岗位评分、事实补齐等）属于数据操作，不是软件变更，不入此册。

## [Unreleased]

### Changed

- **破坏性变更 · 五个技能统一加 `jwb-` 前缀**（PR #25）：`apply → jwb-apply`、`jd → jwb-jd`、`recruit-coach → jwb-recruit-coach`、`resume → jwb-resume`、`track → jwb-track`。
  - **为什么改**：技能身份 = **目录名 = frontmatter `name`**，同名会被宿主**静默覆盖**（不报错）。原名 `apply / jd / resume / track / recruit-coach` 全是高概率通用词，装到用户级 `~/.agents/skills/` 等于拿五个通用词去跟别人已装的技能抢位置——谁被覆盖、覆盖的是谁，都不会有任何提示。
  - **升级后需要你做一件事**：删掉宿主目录里残留的旧名副本，否则旧技能仍在被加载、与新名并存（改名等于没生效）。项目级目录用 `python tools/install_skills.py --prune --target all`（`--prune` 只清理这五个已知旧名、且只作用于**项目级**目标——codebuddy / claude / agents / codex 四处都会处理）；用户级 `~/.agents/skills/` 是**多项目共享位置**，脚本判断不了归属，请手工删除 `apply/`、`jd/`、`recruit-coach/`、`resume/`、`track/` 五个目录，再重跑 `python tools/install_skills.py --target user`。
  - 技能描述同步补了**英文触发词**（原描述只有中文场景，英文请求不会激活对应工作流），并补齐 `compatibility` 环境声明。

### Infrastructure（贡献者可见）

- 新增技能校验的**唯一实现** `tools/check_skills.py`：frontmatter 是否闭合、`name` 是否等于目录名、`description`/`compatibility` 是否齐全、**全局 `name` 是否唯一**。CI（backend job）与 `tools/install_skills.py` **共用这一个实现**——规则写两处迟早分叉，而分叉掉的那一半正好就是没拦住的那一半（本仓库在提交信息治理上已经吃过这个亏）。
- `tools/install_skills.py` 改为「先校验、再分发」：不合规或重名**直接拒绝分发**并给出可读原因。坏技能装到宿主侧只有两种下场——被跳过，或被静默覆盖，两种都不报错，所以装之前是唯一能拦住它的时机。演练模式（--dry-run）同样先校验。新增 `--prune`：清理改名后残留的旧名目录（仅项目级目标生效，共享的用户级目录不自动删）。
- `.codebuddy/skills/` 出库：它是分发脚本的生成物，入库即第二份真源——改 `skills/` 忘了同步它，漂移就产生了。（`.claude/` `.agents/` `.codex/` 三份副本本就被 gitignore，不受影响。）

## [0.1.1] - 2026-09-09

### Changed

- 全站视觉升级（PR #9 / #10 / #11）：设计 token 层重做——背景更深邃、卡片层次拉开并「浮起」（柔和阴影 + 1px 内高光）、前景文字提亮；新增阴影 / 主色光晕 / 渐变 / 径向光晕视觉变量与 `ease-premium` 缓动。全部为 CSS 变量与 Tailwind 类，零运行时开销，尊重 `prefers-reduced-motion`。
- UI 原语外观增强：按钮主色渐变 + 光晕 + hover 抬升，卡片渐变底 + 内高光，徽章字重与间距饱满化，输入框聚焦光晕（边框转主色 + 半透明光环），弹窗与下拉浮层加深层阴影与遮罩，Tab 活动态渐变高亮，骨架屏由透明度脉冲改为 shimmer 横扫。
- 页面级增强：看板统计卡数字改白→主色渐变文字；导航活动项主色光晕指示、顶部径向光晕；追踪表行 hover 左侧主色条（占位边框实现，无布局位移）；进展页子 Tab 由自绘按钮换 Radix Tabs（键盘可达、焦点环）；岗位池评分数字渐变突出；简历工坊 A4 预览加纸张阴影；README 七张截图全量更新为升级后界面。

### Infrastructure（贡献者可见）

- CONTRIBUTING PR 门槛加入「合并前的显式审查记录」：逐文件通读 `gh pr diff`（重点：隐私与四道门、API 消费面、改动是否纯增量），审查结论（含发现的问题与处理决定）必须以评论落进 PR，发现问题当场修或记入后续，不许静默合并——单人开发也让 PR 页面可追溯「审出了什么」。
- 新增 [docs/maintenance.md](docs/maintenance.md)：发布节奏、issue 首响 48h 承诺、极简 labels（bug/feature/docs）、关闭必留结论、每周 1–2 个自然 PR 的维护节奏。
- 审查实践样例：PR #11 审查抓出 `hover:border-border-strong` 静默失效（tailwind colors 缺 `border-strong` 变体映射，类不生成 CSS 且构建不报错），当场修复并以构建产物 grep 验证。

## [0.1.0] - 2026-09-08

### Added

- 本地 Web 原型：看板、投递追踪表、岗位池三个页面，FastAPI 后端直接复用 `tools/` 脚本读写同一份 Markdown/CSV 数据。
- 素材库页面：简历工坊与事实库的文件浏览、PDF/图片内联预览。
- 一键启动脚本（`web/start.ps1`）：起停前后端、等待就绪、自动打开浏览器；含依赖预检（python/node/npm）、端口占用诊断、前端启动失败的分类人话提示。
- 岗位详情页评分下钻：总分 → 四维 → 逐条命中明细（能力分层徽章 + 证据标签徽章）。
- 资格硬门槛前置：解析卡的硬门槛结论（通过/不通过/待确认三态）置顶展示于分数之上。
- 工作区一等概念：后端支持 `--workspace` 参数与环境变量指定默认工作区；`/api/workspaces` 列出可用工作区；前端导航栏切换下拉，所有请求携带工作区参数，多工作区数据隔离。
- BYOK Provider 设置页：OpenAI 兼容 base_url + key 的本地配置（key 脱敏存储）、连通性测试（列模型）。
- 投递追踪模型硬化：新增「状态原因」列；终态（已挂/已放弃）不可回退阶段；同公司+岗位去重拦截；进入终态强制填写原因。CLI、API、前端三端同一套校验（`tools/tracker.py` 为单一事实源）。
- 领域插件体系：`template/profiles/<domain>/` 可插拔领域目录，新增领域不改代码；以无关领域（software-backend）验证通过。
- 六大模块模板：`template/workspace/` 提供全部模块的填写引导骨架。
- Electron 桌面壳：主进程探测打包后端（优先）或本机 Python（回退）→ 拉起后端 → 轮询就绪 → 开窗加载 → 退出时杀进程树；前端静态产物由后端同源托管。
- PyInstaller 后端打包（onedir）：独立 exe 免 Python 环境；`scripts/build_backend_exe.ps1` 一键构建；`pathres.py` 处理打包/源码双模式路径与可写数据目录回退（便携模式 → 系统用户目录）。
- 追踪增强：看板统计卡、漏斗柱、方向、批次可点击下钻（跳追踪表并预置筛选）；状态变更时间线（每次字段变更入账独立 `history.csv`，追踪表行内展开查看）；阶段停留天数（超阈值高亮）；静默提醒（非终态记录长期无进展在看板独立成卡，默认阈值 14 天）；关键字搜索（公司/岗位/备注）与排序（下次动作日期/评分/停留天数）；下次动作日期就地编辑与看板待办一键顺延 7 天。时间线读写与停留天数计算集中于 `tools/tracker.py`，CLI 与 Web 共用。
- 简历数据驱动「标准版式」：`tools/resume_build.py` 新增 `render` 子命令，由 `02_简历工坊/source/resume_<版本>.json` + 内置 HTML 模板渲染出 A4 PDF；`render` 额外断言 A4 纸型（防模板漏 `@page` 导致 Letter）。无子命令时仍直接打印手写 HTML，两条路径并存。
- 简历工坊页（Web）：左结构化表单、右 A4 实时预览，编辑即时写回 JSON；生成 PDF 后回显 ATS 三项与纸型校验结果；含防超页护栏（超一页时提示并禁用生成）与诚实红线常驻提示。新增 `/api/resume*` 路由。
- 简历工坊信息架构调整（双模式）：「标准版式」= 数据驱动编辑，支持在页面上直接新建版本（不再要求手工放 JSON）；「高级模板」= 手写 HTML 精排版的只读浏览与一键生成，文件能力自素材库迁入（`/api/resume/templates*`）。素材库只保留事实库，消除同名「简历工坊」的混淆。
- 工程底座（P0）：原子写（tmp + `os.replace`，统一 `.jobws_tmp_` 临时前缀，改造全部 CSV/JSON/PDF 写路径）；整包导出 zip（保留原格式可独立阅读，UI 明示「包含真实简历」与「不含快照」）；快照备份到系统用户目录（工作区之外，Syncthing staggered 保留策略）；设置页新增「数据与隐私」区块（导出 / 立即备份 / 打开数据目录 / 无遥测声明 / 上次备份时间）。
- 面试记录与日程（P1）：新增 `05_投递追踪/interviews.csv`（`面试id` 外键关联追踪表，公司/岗位自动带出），CLI `tracker.py interview add|list|show|update`，记录自动入账变更时间线；「进展」页左列表右详情（问题/回答/复盘三段式），48 小时内待定面试琥珀高亮；一键导出 `.ics` 日程（RFC 5545 手写实现：CRLF、UTF-8 安全折叠、提前 1 小时 VALARM）。
- JD↔简历差距清单（P1）：`jd_score.py --gap` 与岗位详情「简历差距」面板，把「补关键词」拆成**可召回**（母版里有，召回不构成编造）与**真实缺口**（只能补经历）两类，直接服务诚实红线；不要求解析卡存在，简历版本缺省回退最新。
- 招聘方联系人与 Offer 对比（P2）：`contacts.csv` / `offers.csv` 独立外键文件，CLI `contact` / `offer` 子命令；「进展」页联系人卡片网格（超期跟进琥珀高亮、一键「已联系」）；Offer 横向并排对比**只展示已知事实、绝不给建议**（页脚固定声明，端点零推荐逻辑）；offer 记录自动入账时间线。
- 版本谱系（P2）：按追踪表「简历版本」列聚合展示「该版本投了哪些岗位、各处于什么阶段」，简历工坊底部只读展示。
- AI 简历改写 + 反编造护栏（P2）：`POST /api/resume/{version}/suggest` 走 BYOK 生成改写建议；反编造条款由 `tests/test_prompt_guardrails.py` 12 项断言锁死（删句即测试失败）；本地校验器五项（空改动/结构漂移/身份字段/字数爆炸/新增数字）不过则默认禁用采用，须用户显式确认；端点与前端均不静默落盘。
- 周期复盘（P3）：看板新增复盘区块——阶段转化率（从变更时间线重建「到达过」的阶段，非当前存量）、各阶段停留天数（中位数）、失败归因（按状态原因聚合）。
- schema 自检（P3）：`tracker.py check` 与 `GET /api/system/check`，校验列完整性/必填/日期/枚举/外键；schema 版本 sidecar（`.schema.json`）；无法解析的坏文件自动隔离到 `quarantine/` 并在 UI 展示清单，绝不静默丢弃。
- 「我拒绝的 offer」终态（P3）：与「已挂/已放弃」并列但语义区分——拒绝是双向选择不算失败，复盘归因独立统计，UI 徽章中性绿。
- 简历一键导入（第一批）：上传 PDF/Word(.docx)/Markdown/纯文本 → 抽取纯文本 → BYOK 模型结构化 → **核对页逐段确认后才落盘**。诚实红线「导入=抽取而非生成」由 `IMPORT_CLAUSE` 条款 + 可溯源校验（字段值必须是原文子串、数字必须来自原文，缺失留空）双保险锁死，护栏测试扩至 33 项（删句即失败）；未抽到的字段标黄、疑似补全标红。上传文件只在本机临时目录短暂驻留，用完即删。
- 追踪表 CSV 批量导入（第一批）：粘贴或上传 CSV，两阶段流程——preview 出差异表（新增/重复/错误三态分色，行号 + 原因），commit 持锁重校验后批量写入并逐条入账时间线，冲突整批拒绝；CLI `tracker.py import --file [--dry-run]` 与 Web 共用同一套校验。
- 导出 Word（第一批）：`GET /api/resume/{version}/doc` 零依赖另存 `.doc`（复用 PDF 渲染链路），按钮旁固定标注「Word 版只保证文本可复制，排版以 PDF 为准」。
- 面试题库（第二批）：「进展」页新增「题库」子 Tab，把面试记录里的问题/回答要点/复盘按公司+岗位归集成库，支持关键词检索——面过的问题沉淀为可复用资产，纯只读无新数据文件。
- 投递健康度（第二批）：`tracker.health_score()` 纯函数给出四态判定（紧急=距截止 ≤3 天仍未投 / 逾期=下次动作已过期 / 停滞=停留超阈值 / 正常），**给理由不给黑箱分数**；追踪表新增健康度排序与行内徽章（hover 看理由），看板新增「待推进」清单卡（点击下钻并预置健康度排序）。
- 失败原因聚类（第三批）：看板复盘新增「失败原因聚类」，按工作区 `config/failure_keywords.txt`（每行「类别=关键词」，随领域插件分发）把失败原因归成几类，回答「到底败在哪一类」；未配置文件时退化为「状态原因」原文频次，**绝不虚构分类名**；失败记录少于 3 条时明确显示「样本太少，暂不展示」。
- JD 链接抓取（第三批）：岗位池新建时可粘贴网页链接抓取正文存为 `JD原文.md`（去脚本与标签、按页面编码解码、记录来源与抓取时间、原子写）。抓取失败或正文过短（<80 字）**明确降级**提示手动粘贴，绝不把半截内容当成抓取成功，也不会留下空壳岗位目录。

### 开源发布（Infrastructure，贡献者可见）

- 以 **MIT** 协议开源；新增 `LICENSE` 与 `THIRD-PARTY-NOTICES.md`（Python / 前端 / 桌面壳依赖许可清单）
- 新增 CI（GitHub Actions）：push / PR 跑后端测试（33 项）与前端构建；开发依赖见 `web/backend/requirements-dev.txt`
- 多 AI 工具治理入口：`CLAUDE.md` / `CODEBUDDY.md` / `.github/copilot-instructions.md` 均指向根 `AGENTS.md`（唯一事实源）；新增 PR 模板与行为准则
- **隐私**：`personal/` 真实工作区整体移出版本管理并清洗全部历史——本仓库不含任何真实个人数据（`.gitignore` 整体忽略，本地使用不受影响）

### Changed

- 项目更名：由「秋招工作台」统一为「求职工作台」（显示名与文档；目录名与历史归档不变）。
- 架构重构：由单用户个人工具重构为通用工作台——工具层（tools/skills）/ 领域插件层（template/profiles）/ 用户数据层（personal）三层单向分离。

### Fixed

- 目录重组后 68 处内部路径引用断链。
- 链接修复脚本深度补偿不幂等、归档说明被误改。
- 素材库页面偶发黑屏：hash 路由 + ErrorBoundary 兜底。
- 一键启动脚本的三层路径定位缺陷（`$PSScriptRoot` 空值、路径层级等）。
- 岗位列表页评分一致性问题。
- 岗位详情页展开逻辑的空值隐患（`tsc -b` 构建期暴露）。
- 数据目录根语义错误（工作区根误用工作区目录本身，导致默认工作区标识失效）。
- 工作区切换在 reload 后失效（未持久化选择，reload 丢回默认工作区）：改为 localStorage 记忆上次选择，重载后优先恢复。
- 首屏工作区竞态（内容区在 `listWorkspaces` 设好全局工作区前 mount，切到非默认工作区 reload 会先渲染一次默认数据）：以"工作区就绪后才渲染内容 + 工作区作 key 强制重挂"修复。
- 生成 PDF 时后台读 stderr 触发 `UnicodeDecodeError`（Windows 下以 locale/GBK 解码 Chrome 输出）：改为丢弃浏览器输出，只以 PDF 是否生成判成败。
- `verify_pdf` 的 ATS 关键事实清单依赖模块级全局，Web 并发下会互相覆盖：新增 `facts_file` 显式参数，Web 场景必须传入。
- 静态资源缓存策略缺失导致「改了功能界面没变化」（浏览器按启发式缓存旧 index.html/JS）：HTML 强制协商缓存（`no-cache`），带内容 hash 的 assets 长缓存 `immutable`。
- 高级模板预览版式失真：改为按 A4 宽（794px）渲染再等比缩小（原先全宽渲染行宽达真实的 1.6 倍），高度按 iframe 内容真实高度展开（原先写死高度会截断内容）。

[Unreleased]: https://github.com/chenxiang6663635/job-workbench/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/chenxiang6663635/job-workbench/compare/v0.1.0...v0.1.1
[0.1.0]: https://keepachangelog.com/zh-CN/1.1.0/
