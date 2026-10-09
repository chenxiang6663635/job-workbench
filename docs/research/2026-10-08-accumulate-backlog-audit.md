# 不发布积累期候选清单：修改 / 优化与新增功能审计

日期：2026-10-08 ｜ 范围：`chenxiang6663635/job-workbench` 全仓（main = `4fc71f5` 后）｜ 计划：`2026-10-07-accumulate-backlog-plan.md`

## 执行摘要

应「继续积累、暂不发布」的决策，本审计用四路并行侦察（已登记待办、工程与后端、前端/文档/站点、外部同类工具对照）加公众号渠道交叉印证，产出积累期候选清单。总体判断：代码面相当干净（前端 TODO 字面量为零、a11y 豁免清单为空、错误码与锁名已收口），但存在一个已亲手复验的评分正确性缺陷——小数总分 74.5 会静默落进「不投」档——以及一批小成本高价值的修点和登记漂移；新增功能侧，内部候选池已有十余项带触发条件的登记，外部对照补充了三个与「本地优先」边界相容的方向（JD 深度适配闭环、按 JD 定向模拟面试、offer/薪酬比较）。建议按「取号前小修批 → 积累期主线批 → 触发条件驱动批」三桶推进，凡涉及发布物形态与元数据的项须赶在 26.11.0 取号（落章）之前决策。

## 背景与方法

26.11.0 定于十一月发车，冻结期自取号/落章开始，因此积累窗口为现在至十一月初取号之前。审计由三个 code-explorer 子代理（登记面、工程后端面、前端文档面）与一个外部研究子代理并行完成，另用搜狗微信检索（近 180 天窗口）做中文信息源交叉印证；其中影响最大的两条正确性发现已由本人回到源码逐行复验。已开的三个 issue（#274 笔记返回栈、#259 数据根实施跟踪、#204 Electron `main.js` 拆分）与远端 8 个已合并未删分支作为已知输入计入，不再重复展开。

## 一、修 / 优化

### 1.1 正确性（小成本，建议取号前清掉）

评分链路的档位判定存在真实缝隙：`packages/jobws-core/src/jobws_core/jd_score.py:40-46` 的 `THRESHOLDS` 用整数闭区间（75-100 / 60-74 / 45-59 / 30-44 / 0-29），而维度解析正则允许小数分子（`:84`），`verdict`（`:101-105`）在无匹配时静默回落最后一档——**总分 74.5 会输出「不投／终止，不生成任何材料」**，看板分布（`web/backend/routers/dashboard.py:55-57`）同样错档。此条已亲自复验。

| # | 问题 | 证据 | 影响 | 成本 |
|---|---|---|---|---|
| 1 | 评分档位整数闭区间 + 静默兜底，小数总分错档 | `jd_score.py:40-46,84,101-105`（已复验） | 正确性（决策核心） | 小 |
| 2 | 未指定 `--domain` 时按字母序取第一个插件（`hvac-cooling` 排在 `software-backend` 前），错词典不报错仅 warning；工作区分支把父目录名当插件名 | `jd_score.py:326-338`（已复验） | 正确性 | 小 |
| 3 | CLI 侧默认工作区解析零校验：`JOBWS_WORKSPACE` 越界值静默读写；Web 已 fail-closed（`web/backend/deps.py:104-114`）、MCP 由 `containment.within_any` 兜住，CLI 是唯一静默口 | `packages/jobws-core/src/jobws_core/pathres.py:199-213`、`tools/tracker/_cli_misc.py:223,241-245` | 安全/一致性 | 小 |
| 4 | 两段式令牌簿记三连：非原子写（`approval.py:154-155`）、系统 TEMP 的 `jobws-approvals` 无任何清理实现（明文业务载荷滞留，docstring 却称「已被清理」）、`apply` 先焚毁令牌再持锁（`:190-196`）导致锁超时提示「稍后重试」失真 | `packages/jobws-core/src/jobws_core/approval.py:154-155,180-182,190-196,232-235` | 正确性/数据卫生 | 小 |
| 5 | 渲染临时文件 `__preview_<version>.html` 不守 `TMP_PREFIX`（`.jobws_tmp_`）约定，崩溃残留会混进导出/快照 zip 并被列成可浏览模板 | `tools/resume_build.py:352`、`web/backend/routers/resume.py:472` | 正确性（低概率） | 小 |
| 6 | `history.csv` 追加写非原子（锁内但崩溃可留半行），坏半行会把**整份时间线**送进 `quarantine/` | `packages/jobws-core/src/jobws_core/tracker/applications.py:81`、`tracker/_core.py:128-135` | 正确性（低概率高影响） | 中（需在追加原子化与读侧单行容错间做方向决策） |

### 1.2 测试盲区

评分与差距链路是决策核心却几乎没有直接单测：`jd_score.py` 的 `parse_score_section`(:53)、`parse_dimension`(:78)、`verdict`(:101)、`parse_dimension_detail`(:196)、`parse_lexicon`(:391)、`gap_analysis`(:490) 全部无单元测试，仅 `tests/test_cli_surface.py:372` 一条端到端命中；JD↔简历差距端点（`web/backend/routers/jobs.py:471-501`，含「缺省取最新简历版本」分支）与 MCP 只读工具（`mcp/jobws_mcp/tools_readonly.py:424-428`）零覆盖；`mail_dates.py` 的相对日/工作日换算（`:77-144`）无直测——这正是该模块自述反向结论高发区。加上历史遗留的「硬门槛判定零测试」，构成一个同型测试批（成本均为小）。

### 1.3 性能与规模水位

| # | 问题 | 证据 | 成本 |
|---|---|---|---|
| 1 | 解析卡同一请求内被读两遍解析两遍（列表/看板/详情皆然），岗位池规模线性放大 | `web/backend/routers/jobs.py:91-101` 与 `:140-157,166,179,201`；`dashboard.py:82-90`；`:459-461` | 小~中 |
| 2 | dashboard 单请求多次全量读 `tracker.csv` 且未接现成的两级指纹缓存（`workspace_io.dir_fingerprint` 仅 `/api/sync` 在用） | `dashboard.py:182,191`、`jobws_core/workspace_io.py:247-300`、`sync.py:29` | 中（先量再动） |
| 3 | pytest 61s 越阈但无 durations 观测：约 25 次完整模板+demo 目录复制（`test_demo_workspace.py` 19 处 + `test_init_workspace_guard.py` 6 处）、40+ 模块函数级 `TestClient` 夹具；先加 `--durations` 固定 top-N 再上 xdist | `pytest.ini`、`tests/test_demo_workspace.py`、`tests/test_init_workspace_guard.py` | 小（观测先行） |
| 4 | 9 个豁免文件「实际=登记」贴线（任何 +1 行即触发只许变小）：`resume.py` 614、`jobs.py` 502、`system.py` 332、`question_bank.py` 595、`status_parse.py` 329、`mail_facts.py` 317、`dataroot_manifest.py` 330、`server.py` 354、`tools_readonly.py` 429 | `tools/size_allowlist.txt`（8 行还登记着「后续拆分」） | 中（挑 1~2 个发版前主动拆） |
| 5 | 前端无路由级代码分割（8 页同步 import，prod bundle 约 424KB）；追踪表/邮件台账全量渲染无虚拟化、后端列表无上限 | `web/frontend/src/App.tsx:5-12`、`vite.config.ts:50-75`、`ApplicationsTable.tsx:95`、`MailList.tsx:357`、`applications.py:190` | 中 |
| 6 | 微观重复：overdue 过滤同一行 `parse_iso_date` 调两次 | `web/backend/routers/applications.py:169-170` | 小 |

重复实现收编（小成本）：「路径片段越界」三处实现且错误码分叉（`containment.py:86-108` 自称唯一原语，但 `mcp/jobws_mcp/paths.py:161-179` 手写同规则、`web/backend/deps.py:281-287` 内联弱化版 → 同义输入拿到 `path.illegalSegment` vs `path.escape` 两种错误）；严格 ISO 日期解析两份（`tracker/_core.py:139-150` 与 `question_review.py:26-38`）；「CSV 读取 + restore_row」两份（`tracker/_core.py:128-135` 与 `question_bank.py:64-65`）。

### 1.4 前端 / 文档 / 站点

| # | 问题 | 证据 | 成本 |
|---|---|---|---|
| 1 | 错误文案承诺「到设置页重新选择数据根」，但设置页只有引导式迁移，后端 `GET/POST/DELETE /api/system/data-root` 前端零调用 | `web/backend/routers/data_root.py:100-123`、`web/frontend/src/api.ts:421-444`、文案 `zh-CN.ts:1135` | 中 |
| 2 | 应用内「使用手册」仍指 Gitee 纯 Markdown，站点上线后未回切 | `web/frontend/src/components/settings/AboutCard.tsx:69-78` | 小 |
| 3 | 笔记图片一律渲染「已跳过」占位（代码注释自注需新增笔记侧只读文件端点） | `NotesMarkdown.tsx:164-181` | 中 |
| 4 | 题库三态徽章直出中文数据值（未看/看过/会了），同枚举在训练侧走 `t()`——英文界面出现中文徽章 | `BankCounts.tsx:34-36`、`QuestionBankRow.tsx:43` vs `ReviewQueue.tsx:274` | 小~中 |
| 5 | 简历强调色 swatch 的 `aria-label`/`title` 用后端中文色名 | `Resume.tsx:403-411`、`resume.py:176` | 小 |
| 6 | a11y 三小项：无「跳到主内容」链接（`App.tsx:96-221`）；表格排序提示只挂 `title`（`ApplicationsTable.tsx:47`）；axe 只挡 serious/critical、对比度 moderate 被排除（`e2e/a11y.spec.ts:9-11`） | 同左 | 小~中 |
| 7 | 390px 基线缺 3 页（prepare/resume/library）；整站适配未做（候选池登记，成本大另列） | `web/frontend/e2e/viewports.spec.ts:14-24,51` | 小（补基线） |
| 8 | 术语表与 docs 索引全中文，EN README 却以 "Glossary — defined once" 直推英文读者；用户可见模板（`template/AGENTS.example.md`、`template/workspace/README.md`）全中文且 `init` 原样复制进英文用户工作区 | `docs/glossary.md:1-40`、`README.md:174,44,90-94` | 小~中 |
| 9 | **站点口径待收敛**：GitHub Pages 确认在线且源 = `site-dist` 分支（该配置在 GitHub 仓库设置里，不在仓库文件内——子代理「无部署步骤」系据此误判，已修正）；真正待办是①核实 EdgeOne 与 github.io 双通道当前是否都活着，②「Gitee 镜像」文案给读者「在线站国内可达」的期待但实为仓库镜像（非渲染站点），③下载备用通道是循环依赖（打不开 GitHub → 去 GitHub Issues 留言，Gitee 附件 ≤100MB 装不下 122.74MB 包） | `README.md:167`、`README.zh-CN.md:143`、`.github/workflows/site.yml:5-6,105-129`、`site/content/download.tmpl.md:15-19`、`docs/specs/2026-09-28-project-site-design.md:53` | 小（核实+改文案）/ 中（国内直链另列） |
| 10 | 截图新鲜度无发版核验项（release-checklist 只核下载页版本号）；EN 站明暗切换提示固定中文 | `docs/release-checklist.md:65`、`site/mkdocs.yml:20,24,61` | 小 |
| 11 | 登记漂移两处：ROADMAP 的 P2-1..P2-5 勾选框仍是 `- [ ]` 而 CHANGELOG Unreleased 已记录完成实测（`ROADMAP.md:39-54` vs `CHANGELOG.md:34-38`）；站点 spec Task 1–7 勾选框全空 | `ROADMAP.md:39-54`、`docs/specs/2026-09-28-project-site-plan.md:61-123` | 小 |

### 1.5 治理与登记

远端 8 个已合并分支未删（本地已清）；DSH 对 MCP 只读资源 `jobws://` 的支持待真机核验（三个技能把它当 JD 正文唯一读法，结构性盲区）；CodeQL 属 #207 登记的 follow-up；出网能力「先更新矩阵再改代码」尚无 CI 自动校验（`docs/data-flow-matrix.md:40-42`）；`tools/legacy_imports_allowlist.txt:29-34` 的 tracker/approval 水位 9 待归零删 shim；#204 在 CHANGELOG 26.10.0 段有交付记录但 issue 仍开放，需人工核对剩余范围后关单或继续。

## 二、新增功能候选

### 2.1 内部已登记（按触发条件/成本）

整站 390px 适配（大）；追踪表/邮件台账虚拟化或后端分页（中）；路由级懒加载（中）；数据根设置页「直接改路径/清除选择」入口（中，补齐 1.4-1 的承诺缝隙）；笔记图片渲染（中）；用户可见模板双语化（中）；国内安装包直链通道（中-大，Gitee 发行附件 ≤100MB 装不下 122.74MB 包，需网盘/对象存储）；应用内手册回切在线站点（小）；Outlook 个人 OAuth2 IMAP（大，调研已完成、触发条件成文）；托盘常驻+开机自启（候选池）；ICS RRULE / 提醒完整版（候选池）；浏览器表单预填、宿主内渲染面板（候选池）；winget 分发（中，随发布节点）；代码签名（触发条件三条，暂缓）；Electron 33→44 主版本升级（大，人工批次）；macOS 支持（大，签名阻碍）；更多领域插件；schema 迁移脚本（sidecar 已预留，v1 无破坏变更暂不需要）。

### 2.2 外部对照（需先论证再入池）

外部研究（GitHub/web）与公众号检索（近 180 天）交叉印证出三个共同热点：**JD 深度适配重于语言润色**（中文源：智联校园 2026-09-24、科研数字化 2026-03-17 均以「能否围绕 JD 深度匹配与针对性改写」为选型标准；英文源：ATS 厂商叠加 AI 筛选层与匹配分）、**AI 模拟面试**（中英两源都在近一年集中爆发）、**简历「AI 味」与反 AI 筛查**（青媒计划 2026-03-20 提到企业用「反 AI」工具筛简历——与本项目诚实红线天然契合）。据此的候选方向：

| 方向 | 一句话 | 依据 |
|---|---|---|
| 按 JD 定向模拟面试出题 | 题库→按 JD 生成定向题组+复盘链路（已有 bank drill 与复盘卡，增量小） | 中英两源热点；`bank drill` 现状 |
| offer/薪酬差比较 | 多 offer 条款与薪酬差本地分析（敏感数据恰是本地优先优势场景） | career-ops `salary-gap` 思路 |
| 简历「AI 味」自检 | 面向反 AI 筛查的生成度/个性化检查，输出改写建议而非代写 | 公众号「反 AI」信号 + 诚实红线 |
| 浏览器扩展一键收职位 | 招聘页一键书签进看板（Teal 式）；前置依赖 = 技术债清单里的「本地 API token」 | Teal 扩展形态 |
| JSON Resume JD schema 对齐 | jsonresume 新增 `job-schema.json`（JD 字段 draft），可作 JD 解析的导出/互操作格式 | jsonresume/resume-schema |
| JSCalendar bis 跟进 | RFC 8984 的 bis 草案（2026-01 第 14 版，Aug 2026 提交 IESG）新增 `virtualLocations`/`alerts`/`recurrenceOverrides`，对面试日程+提醒建模更精确，与「提醒完整版/ICS RRULE」候选连线 | IETF datatracker |

### 2.3 反面清单（明确不做，与既有边界一致）

云端收件箱同步/服务器存邮件正文（Gmail `gmail.readonly` 属受限范围，服务器存储需安全评估——本机解析恰是合规优势）；账号体系与多租户；拆第二仓库（7 信号未触发）；第三方简历托管；自动投递/自动发邮件（触犯门户 ToS，坚持「AI 起草、人来提交」）；简历直传云端 AI 供应商（若宣称「零上传」需把口径限定为「不经本项目方服务器」，或支持本地模型）。

## 三、分析与综合：三桶推进

桶一（取号前小修批，建议立即排期）：1.1 全部（除 history.csv 方向项）、1.2 的 jd_score 纯函数测试群、1.4 的登记漂移回填与站点口径核实、1.5 的远端分支清理、截图重跑进发版清单。理由：全是小成本、互不阻塞，且「verdict 错档」这类决策核心缺陷不应带进发布。

桶二（积累期主线，十一月初取号前按周推进）：gap 链路与 mail_dates 测试、解析卡/dashboard 读放大优化（先 durations 后动手）、重复实现收编、贴线文件拆 1~2 个、路由懒加载与长表虚拟化、数据根设置页入口、笔记图片端点、模板与术语表双语、CodeQL、DSH `jobws://` 真机核验。理由：这些是「继续积累」的主体，且多数在发布节点前完成能让 26.11.0 的 Release 说明更扎实。

桶三（触发条件驱动，不主动开工）：390 整站、托盘、ICS RRULE、Outlook OAuth2、Electron 升级、代码签名、winget、国内直链、macOS、marketplace 收录（必须在 npm 首发之后）。凡涉及发布物形态与元数据者（代码签名、winget），要么赶在取号前落定，要么顺延到 26.11.x/26.12.0。

## 四、结论

回到原始问题——「还有哪些要修/要优化、还有哪些功能该补」：修的清单集中在两处，一是决策核心的小成本正确性缺陷（评分档位缝隙、插件回退、CLI 工作区校验、令牌簿记），二是登记漂移（ROADMAP/spec 勾选、站点口径）；优化的清单集中在测试盲区、读放大与 9 个贴线文件；新增功能的内部池已足够厚，外部对照额外贡献了三个与本地优先边界相容的方向。建议下一步直接把桶一切成第一个 PR 批次开工，桶二按周排期，桶三维持触发条件不动。

## 局限性

三个子代理的行号结论未逐条复跑验证（本人在合成前复验了 1.1 的前两条，并修正了子代理对站点部署的一处误判——GitHub Pages 源配置在仓库设置级而非仓库文件）；pytest 耗时为结构性推断而非实测排行；#204/#259 的交付范围需人工核对后才能定处置；外部来源多为产品自述页与中文二手聚合（文中已分层标注），career-ops 的功能清单无日期锚点；公众号检索经搜狗聚合、References 中的跳转链含会话 token 可能随时失效（按「标题+公众号+日期」可检索原文）；成本估计均为侦察级（小/中/大），实施前需各自立简报。

## References

1. [Issue #274 笔记互链返回栈](https://github.com/chenxiang6663635/job-workbench/issues/274)
2. [Issue #259 单一 canonical 数据根实施跟踪](https://github.com/chenxiang6663635/job-workbench/issues/259)
3. [Issue #204 Electron main.js 拆分](https://github.com/chenxiang6663635/job-workbench/issues/204)
4. [career-ops（GitHub，本地优先 AI 求职代理）](https://github.com/santifer/career-ops)
5. [Gmail API scopes（受限范围与安全评估要求）](https://developers.google.com/gmail/api/auth/scopes)
6. [jsonresume/resume-schema（含 job-schema.json draft）](https://github.com/jsonresume/resume-schema)
7. [HR Open Standards Schema](https://schema.hropenstandards.org/)
8. [RFC 5545 (iCalendar)](https://www.rfc-editor.org/info/rfc5545/)
9. [JSCalendar bis 草案第 14 版（2026-01）](https://datatracker.ietf.org/doc/draft-ietf-calext-jscalendarbis/14/)
10. [Teal Job Tracker（浏览器扩展形态）](https://www.tealhq.com/tools/job-tracker)
11. [公众号：AI简历优化工具推荐｜智联校园 2026-09-24](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSzMET5g_tS2ybDmpuZ5TdsFYbqEr7EYmxVqXa8Fplpd9PBjyuMl4vdDho3aLWmAVgJJzEsRtX7wSihMz7UhKkhN1JdHDAynyzkNAdBczMzzaDyR5hxNApWDeo6hUpf23gNf_-PvdMrgCqMkkBtyEArFylJlh89GgG09zIxA58meTzlwuvEVRmo5CTWBuI3dALNh9ATy_gj93M0sp6jc7TFHYgncbQmLa2fR8BT47ro08rg2Yq1xU8jAoBHT0..&type=2&query=AI%20%E6%B1%82%E8%81%8C%20%E5%B7%A5%E5%85%B7%20%E7%AE%80%E5%8E%86&token=E12AB235D8DB1E94FFF9A2B1ACAE159EFFACCFFC6AC737CE)
12. [公众号：AI简历工具哪个好用？2026年10款对比｜职场百态 2026-10-06](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSzMET5g_tS2ybDmpuZ5TdsFYbqEr7EYmxVqXa8Fplpd9Ls5KmC-oxDGuLJiWYCRUmjtjOwT-lE4aT25L9_PF4GEW9sPZRadNfkZNIQvgvLjOSFZW44TGYrLWJ7D-0dP6OZb3ZJXzOoTUtIF8nD3oyWFJqGxwt6O2upY7n5JgHSAG7dHJPWg2hVwyxLN8wBf8gk3Xqcj3kVMt5i0SL9sdIDmkB5NFbYYh2M2C8h_gOqKs1..&type=2&query=AI%20%E6%B1%82%E8%81%8C%20%E5%B7%A5%E5%85%B7%20%E7%AE%80%E5%8E%86&token=E12AB235D8DB1E94FFF9A2B1ACAE159EFFACCFFC6AC737CE)
13. [公众号：国内求职场景下，AI简历优化工具怎么选｜科研数字化 2026-03-17](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSzMET5g_tS2ybDmpuZ5TdsFYbqEr7EYmxVqXa8Fplpd9Sr3SUO7LckuePXLukg6snfQZRxvRyuy6jf1TPiRBz2ddkPVWzbO1Bt34AnM7nCVZu5zmBVVXk__m5BApsy4dw0chCuKomEJS_lNUyhciYAA9qOpBfsXvthYUTtDsOgvsaoRKbs5O_Q9vSn3ngBRODhNyjCMbSVJsyFDN0DT2_zX0OK9DLfgmPA..&type=2&query=AI%20%E6%B1%82%E8%81%8C%20%E5%B7%A5%E5%85%B7%20%E7%AE%80%E5%8E%86&token=E12AB235D8DB1E94FFF9A2B1ACAE159EFFACCFFC6AC737CE)
14. [公众号：春招避雷！AI 求职教程都是套路｜青媒计划 2026-03-20](https://weixin.sogou.com/link?url=dn9a_-gY295K0Rci_xozVXfdMkSQTLW6cwJThYulHEtVjXrGTiVgSzMET5g_tS2ybDmpuZ5TdsFYbqEr7EYmxVqXa8Fplpd9JD4zYtr7B_nz2VpBO2FlhWiNVQUFkgu-vmoU_Z8W53LPXhzclv1kLle17X6MMiTG-2wNz9B_i6Trpteu3zf7U_1DuB_UbOYpKm1w-dJdF0j3kwqqrVU8jAoBHT0vEVRmo5CTWBuI3dALNh9ATy_gj93M0sp6jc7TFHYgncbQmLa2fR8BT47ro08rg2Yq1xU..&type=2&query=AI%20%E6%B1%82%E8%81%8C%20%E5%B7%A5%E5%85%B7%20%E7%AE%80%E5%8E%86&token=E12AB235D8DB1E94FFF9A2B1ACAE159EFFACCFFC6AC737CE)
