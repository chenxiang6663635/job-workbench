# 研究报告：求职工作台下一步功能差距分析（2026-09-03）

- 日期：2026-09-03
- 查询类型：Breadth-first（四个功能域并行检索 + 主 agent 综合辩驳）
- 数据来源：四路 research subagent 检索；其中"本地优先基础能力""投递后全流程""简历与 JD 匹配"三路完整返回，第四路（AI 增强与岗位发现）中途中断，但该议题由前一轮 `report_job_search_products.md`（BYOK 共识、AIHawk 红线）与本次第一、二路材料充分覆盖，结论不依赖缺失部分。
- 原始问题：还需要开发哪些功能？成熟项目有哪些好功能值得借鉴？
- 与既有调研的分工：2026-08-31 那份是**产品化定位调研**（架构、LLM 接入、差异化机会），本轮是**功能级清单差距分析**。

## 执行摘要

把四路结论叠到本项目现状上，最重要的发现不是一个炫技功能，而是一个**结构性空白**：这个项目在"投递之前"（JD 解析 → 硬门槛 → 四维评分 → 简历生成 → 记入追踪表）已经做到了市面少有的深度，但**"投递之后"到入职之间几乎完全空白**——而这段恰恰是求职周期中耗时最长、情绪消耗最大、也最容易积累复利资产的部分。

同时有三条来自成熟产品的关键启发，成本不高但价值很高：其一，Resume-Matcher 的 **"missing vs injectable" 二分**（区分"JD 里有而简历没有"与"母版里有但这一版没用上"），把"补关键词"从"编造新技能"变成"从母版召回"，直接服务本项目的诚实红线；其二，它把**反编造条款写进提示词并用单元测试锁死**，删句即测试失败，这是把红线从口号变成机制的范本；其三，Obsidian 的**快照必须存在 vault 之外**——备份与源数据同盘同毁等于没备份。

成本最低、收益最确定的三件事（一天内可完成）：整包导出 zip、数据目录一键打开 + 无遥测声明、原子写 + 自有临时文件前缀。而最该克制的是"AI 模拟面试""替用户选 Offer""CRDT 同步"——前者是闭源产品的付费噱头且需云，后两者分别是产品伦理与过度工程的雷区。

---

## 一、投递后全流程：最大的结构性空白

闭源三强（Teal / Huntr / Simplify）在这个阶段实际收敛为同一套能力：**面试日程 + 上下文 → 联系人 → 漏斗指标**。值得注意的是，没有一家做"AI 替你选 Offer"或决策引擎——OfferPilot 明文写着"多 Offer 对比只整理已知事实，最终选择仍由你决定"。开源侧则几乎整体停在投递那一刻，连最成熟的 JobSync（974★，唯一有 Question Bank）和 local-first 的 JobCtrl（86★）都没有联系人与 Offer 模块。

| 功能 | 代表产品 | 成熟度 | 付费墙 | 用户价值 | 成本量级 | 本地无云可行 |
|---|---|---|---|---|---|---|
| 面试日程 + ICS 导出/托盘提醒 | Huntr Interview Tracker、JobCtrl | 高 | 否 | 高 | 0.5–1 人日 | 可行 |
| 面试记录与复盘（沉淀为知识库） | CareerDesk、JobSync Question Bank | 中（很早期） | 否 | 高 | 2–4 人日 | 可行 |
| 多 Offer「已知事实」并排对比 | OfferPilot（唯一实做，7★） | 低 | 否 | 高（低频但致命） | 1–2 人日 | 可行 |
| 招聘方联系人 + 跟进记录 | Huntr Contact Tracker、Simplify | 高 | 否 | 中 | 1–2 人日 | 可行 |
| 漏斗转化 + 失败归因 + 周期复盘 | Huntr Metrics、Simplify Insights | 中高 | 否 | 中高 | 2–3 人日 | 可行 |
| AI 模拟面试 / AI 面试官 | Teal、Simplify（主推付费卖点） | 中 | 是 | 低（噱头嫌疑） | 高 | 不可行（需云） |

几个值得注意的细节：Huntr 的"面试追踪"实测是日历 + JD 关键词高亮 + 私有笔记，**不是题库**；真题库只有 JobSync 的 Question Bank，且它强调的是"我被问到的题 + 我的回答"而非通用面经。**通用面经库不必做**——牛客、一亩三分地已经供给充分，做"绑定到具体岗位的记录与复盘"才有差异化。中文社区的 Notion 模板把流程细分出第 8 个状态"我拒绝的 offer"，这个状态值得抄——它对称地记录了双向选择，而现有九级阶段里没有它。

提醒与通知在本地无云架构下有三条成熟路径：面试/截止日导出 .ics 交给系统日历；Electron 系统托盘 + 原生 Notification；应用内超期高亮。JobCtrl 的 snooze/dismiss 是最省事的交互范式。

**明确排除**：AI 面试官（Teal 与 Simplify 的主推付费卖点，无一手留存数据，且与不联网直接冲突）；自动推荐选哪个 Offer（所有产品都回避，只做并排展示）；地图视图、Live2D 看板娘一类噱头。

## 二、简历与 JD 匹配：从"打分"走向"可执行建议"

这是成熟产品与本项目差异最小、但也是最容易把已有优势变现的一块。我们已经有硬门槛前置与四维可下钻评分——市面没人同时做好这两点——但缺的是"把评分翻译成用户能执行的动作"。

| 功能 | 代表产品 | 成熟度 | 付费墙 | 用户价值 | 实现成本 | 与诚实红线 |
|---|---|---|---|---|---|---|
| JD↔简历差距清单 + 逐条建议 | Resume-Matcher（源码可读）、Jobscan | 高 | RM 免费；Jobscan 重度付费墙 | 高 | 低（可复用现有词典/评分） | 不冲突，反而降低编造动机 |
| diff 式改写（建议 + 用户批准）+ 本地校验器 | Resume-Matcher | 中高 | 免费（BYOK） | 高 | 中 | 有张力，须靠护栏 |
| 封面信生成 | Resume-Matcher、Jobscan | 高 | 同上 | 国内校招低 | 低 | 中（易编造动机） |
| ATS 解析可视化 | OpenResume（启发式规则，非真 ATS） | 中（维护度存疑） | 免费 | 中 | 中 | 不冲突 |
| 版本谱系与投递记录（母版→派生→投了哪家） | Resume-Matcher、RenderCV | 中 | 免费 | 高（多岗海投） | 低-中 | 不冲突 |
| 分享链接 / 模板市场 / 多语言生成 | Reactive Resume、RenderCV | 高 | 免费 | 低-中 | 中-高 | 与本地优先冲突 |
| 脱离 JD 的"简历体检分" | 各 SEO 工具 | 高 | 多为引流 | 低（无锚点） | 低 | 易诱导刷分 |

**"missing vs injectable" 的二分是关键设计。** Resume-Matcher 的 `ats.py` 输出 `missing_keywords` 与 `injectable_keywords`（母版里有、本版没用上的词）。这个区分把"为过 ATS 而补词"从"编造新技能"变成"确认母版里确有其事后召回"，与本项目"永不编造经历"的红线方向完全一致。它的评分公式（关键词 0.55 + 技能覆盖 0.25 + 段落完整度 0.20）可直接作为参考锚点——但我们有自己的四维框架，不必照搬，只需借鉴"输出可执行差异"这一层。

**改写形态必须是 diff 而非重写。** 成熟开源方案是：生成结构化改动 → diff 预览 → 用户确认后 apply。Resume-Matcher 甚至把反编造条款**写进提示词并用测试锁死**（`test_prompt_guardrails.py` 断言提示词必须含 "Do NOT add new work, metrics, or responsibilities"，删句即测试失败），本地校验器再做五项检查：空改动、section 计数漂移、身份字段被改、字数爆炸、新增数字/百分比/金额。它自己承认的盲区是：指标正则漏掉裸计数（如 "led 12 engineers"），叙述层面的编造只剩提示词条款兜底。这提示我们若要实现，应补上**逐句实体/数字/动词升级抽取 + 第二遍 LLM 复核 + 未通过则标红要求显式确认**，而不是静默接受。

一份厂商自评报告（Bloom，2026-07，虚构简历 n=106，非同行评审，数据不可当独立基准）称：无约束改写每次运行引入约 0.2–0.4 个编造事实，加入 grounding 约束 + **独立 verification pass** 后编造降为 0。方向可信（与 Resume-Matcher 源码实践互相印证），数字不可尽信。

**ATS 解析模拟不建议优先**：OpenResume 的实现是启发式规则，是"某个解析器的猜测"而非任何真实 ATS；我们的 PDF 是自产（HTML → Chrome 打印），风险主要在用户手写高级模板，价值中等。

## 三、本地优先的基础工程能力：信任是产品的一部分

这一路的发现最反直觉：**真正拉开成熟 local-first 应用差距的不是功能，而是"用户敢不敢把身家性命放进来"**。而这些能力大多成本极低。

| 能力 | 代表产品（已核实） | 成熟度 | 用户价值 | 成本量级 | 对本项目 |
|---|---|---|---|---|---|
| 应用层快照备份（vault 之外） | Obsidian File Recovery：默认 5 分钟间隔、保留 7 天，存系统目录 | 高 | 安全 | 中 | 必要 |
| 时间机器式保留策略 | Syncthing Staggered：1h/30s、1d/每小时、30d/每天、之后每周 | 高 | 安全 | 低-中 | 建议照抄 |
| 整包导出（可脱离应用独立使用） | Joplin JEX/RAW、Standard Notes 解密导出 = zip（每条笔记独立纯文本） | 高 | 信任 + 反锁定 | 低 | 必要 |
| 分层导出格式（开放格式 + 无损格式双轨） | Anytype：Markdown/HTML/PDF × JSON/Protobuf | 高 | 便利 | 中 | 参考 |
| 每天自动备份 | Standard Notes 桌面端 | 中-高 | 安全 | 低 | 建议做 |
| 同步冲突处理 | Syncthing：绝不覆盖，旧版重命名 `*.sync-conflict-<date>-<time>-<device>` | 高 | 安全 | 0（交给它） | 不必自研 |
| 版本历史 | Obsidian 快照 vs Logseq Git vs CRDT | 中 | 安全 | 高 | 暂缓 |

三个要点。**其一，快照必须在工作区之外**——Obsidian 存系统目录并用绝对路径索引，原因很实际：快照若与源数据同盘同目录，会被用户误删、被 git、被同步工具一并波及，等于没备份。**其二，同步不自研**——把工作区交给 Syncthing 或网盘目录即可，且可沿用 Syncthing 的 `.syncthing.` / `~syncthing~` 前缀命名空间思路，定义我们自己的临时文件保留前缀，让同步工具自动排除。**其三，原子写（tmp + rename）** 把已有的 file_lock 从"并发不打架"补成"绝不写坏"。

schema 演进的处理共识是：每份 JSON 带 `schema_version`、启动时只读扫描、失败项隔离到 quarantine 而非静默丢弃、UI 给出可点击的异常清单。local-first 论文把 schema 演进列为开放问题（没有中央数据库就没有权威 current schema），所以这一层越早建立越省事。

信任表达上，Anytype 把 Storage / Privacy & Encryption / Analytics 列为一级文档页，Standard Notes 提供**离线解密工具**（不依赖其 App 也能解备份）——这两招成本几乎为零但信任收益极高。另有值得借鉴的一点：Anytype 明确写下"并非一切可导出"（Space Members、Chat 因绑定用户密钥无法导出）——**明确写下"导出不包含什么"，比含糊承诺更能建立信任**。

**过度工程，建议排除**：Git 自动提交集成（依赖环境、CSV/JSON 合并语义差、用户门槛高——论文评价 Git 是最接近 local-first 的现成模型，但其弱点恰是"非行文本无能为力 + 需用户懂 Git"，而 CSV/JSON 混合工作区正是这个弱点区）；CRDT/实时协作（论文自述尚不建议用于生产）；端到端加密备份（无云无登录场景收益有限）；自建同步服务（违背无云）。

## 四、AI 增强与岗位发现：BYOK 下什么才值得用户自付 token

这一路的结论与既有调研高度一致，且更强化了一个判断：**AI 是增强层，不是地基**。我们的评分框架设计为人可手动执行（脚本只做校验、AI 做判断、无 AI 也能跑），这正好对应"免费核心 + AI 增强"的切分共识——市面闭源产品也是这么切的（Teal：追踪免费、AI 付费墙）。

按「用户价值 × token 成本 × 出错风险」排序，值得做的是：JD 摘要与关键点提取（低成本、低风险、高频）、简历按 JD 裁剪的 diff 式建议（高价值但需严格护栏）、面试复盘反馈（把我们记录的面试问答转成下次的改进点，闭环价值高）。值得警惕的是：AI 模拟面试（需云、噱头）、薪资谈判话术生成（易编造且高风险）、公司调研（可用搜索替代，AI 边际价值低）。

**AI 输出的信任机制**是这块的真正门槛，成熟范式包括：展示依据与引用来源、diff 预览、可回滚、明确标注哪些内容是 AI 生成的。对本项目尤其重要——我们的红线是"简历每个动词都要经得起 5–10 分钟追问"，所以任何 AI 生成内容都必须是**可追溯、可回滚、可拒绝**的，且默认不自动落盘。

**岗位来源**：不碰自动投递红线的前提下，可行路径是用户手动粘贴 JD、浏览器扩展在用户自己会话内保存岗位、RSS/公开列表订阅。合规边界很清楚：LinkedIn 用户协议 8.2 明禁自动化，AIHawk 的维护者在其仓库主页**自述**收到 cease and desist（当事人自述，出处见 `report_job_search_products.md`）；而扩展只做"用户自己会话内的预填/保存"（Simplify 的做法）风险显著更低。**绝不做的**：代登录交密码、自动点 Easy Apply、批量节流投递。

## 五、综合：差距矩阵与优先级建议

对照本项目现状，把四路发现收敛为三档。

**【缺——且值得做】**

| 优先级 | 功能 | 理由 | 成本 |
|---|---|---|---|
| P0 | 整包导出 zip（保留原格式，可独立阅读）+ 数据目录一键打开 + 无遥测声明 | 纯信任收益，成本极低，local-first 产品的入场券 | 极低 |
| P0 | 原子写（tmp + rename）+ 自有临时文件前缀 | 把 file_lock 从"并发不打架"补成"绝不写坏" | 极低 |
| P0 | 快照备份到工作区之外（系统目录）+ 时间机器保留策略 | 数据安全的底线；Obsidian 的成熟答案 | 低 |
| P1 | 面试日程 + ICS 导出 + 托盘提醒 | 投递后空白中成本最低、感知最强的一项 | 0.5–1 人日 |
| P1 | 面试记录与复盘（绑定具体岗位，沉淀为可复用资产） | 复利价值最高；不做通用题海 | 2–4 人日 |
| P1 | JD↔简历差距清单（含 missing / injectable 二分） | 把已有评分优势变现为可执行动作，且服务诚实红线 | 低（可复用词典） |
| P2 | 多 Offer「已知事实」并排对比（不替用户决策） | 低频但致命；所有成熟产品都回避决策、只做展示 | 1–2 人日 |
| P2 | 招聘方联系人 + 跟进记录 | 标配而非加分项；开源侧普遍缺失 | 1–2 人日 |
| P2 | 版本谱系（母版 → 按岗派生 → 哪版投了哪家） | 多岗海投的真实需求 | 低-中 |
| P2 | diff 式简历改写建议 + 本地校验器 + 反编造护栏（写进提示词并用测试锁死） | 高价值但需严格护栏，是本项目差异化的自然延伸 | 中 |
| P3 | 漏斗转化分析 + 失败归因 + 周期复盘 | 长期资产 | 2–3 人日 |
| P3 | schema 版本自检 + 迁移脚本 + 坏文件隔离 | 越早建立越省事 | 低-中 |

**【有但浅——值得加深】**

- **追踪表**：九级阶段对普通用户过细，业界通行 5–6 级（此前调研已建议高级模式分离）；缺"我拒绝的 offer"这一对称终态。
- **静默提醒 / 待办**：目前是应用内展示，可升级为 ICS 导出 + 系统托盘通知。
- **简历工坊**：标准版式目前不支持内联加粗（关键数字如 52.1% 不加粗影响扫描可读性），schema 演进 v2 可补；高级模板只可浏览生成，编辑仍走手写 HTML。

**【已有且更好——不必跟风】**

- 资格硬门槛前置（市面真空，没有一家做）
- 评分证据可追溯（精确/模糊/语义三档标注；市面仅 MatchMyJD 有类似，且我们是四维度下钻）
- 变更时间线 + 阶段停留 + 静默提醒（开源 tracker 普遍没有这么细的数据模型，JobCtrl 的双轴是唯一可比对象）
- 三层分离与领域插件（把"暖通制冷"换成任何领域只需加目录）

**【明确排除】**

AI 面试官与模拟面试打分（需云、付费噱头）；替用户选 Offer（产品伦理，所有产品都回避）；自动投递 bot 与代登录（AIHawk 收到 cease and desist 的教训，据其维护者自述；LinkedIn 协议 8.2 明禁）；CRDT 与实时协作（论文自述不成熟）；Git 自动提交集成（CSV/JSON 合并语义差且用户门槛高）；自建同步服务（违背无云）；脱离 JD 的"简历体检分"（无锚点、易诱导刷分）；通用面经题库（牛客/一亩三分地已充分供给）。

## 六、一个更根本的判断

这份清单里最该先做的，可能不是任何一个"功能"，而是**把"投递之后"这段空白补上**——哪怕只做面试记录与复盘这一件。理由是复利：投递前的解析与评分，每次投递都要重做；而面试记录与复盘是**越用越值钱**的资产，第二场面试能用上第一场的复盘，同公司的二面能用上一面的记录。这也最贴合这个项目已经建立的气质——它一直在做的是"可追溯、可回溯、可复用"，只是这条链条目前停在了投递那一刻。

另一个判断是：**AI 功能应当等到"差距清单"与"护栏机制"落地后再接**。先把"JD 与简历的差异"用规则和词典算出来（无 AI 也能用，符合项目底线），再让 AI 在这个确定性骨架上做润色与建议，风险可控得多。反过来先上 AI 改写，等于把诚实红线寄托在提示词上——而 Resume-Matcher 的经验恰恰说明，光靠提示词不够，必须有本地校验器与测试锁死。

## 七、局限性

- 微信公众号源未能取回：本环境无 `wechat-article-search` skill，改用中文 web_search，结果以 CSDN/知乎/头条内容农场为主（模板化标题、AI 生成痕迹、日期批量集中在 2025-2026），**未采信其结论**。中文一手有效来源仅 Obsidian 官方中文帮助与其社区文档。国内求职产品（如牛客、实习僧、BOSS 直聘相关工具）与国内用户对 BYOK/付费的习惯差异未被覆盖。
- Teal 官网与知识库（tealhq.com / help.tealhq.com）全部返回 403，其 AI Interview Practice 的付费门槛未核实；Huntr 定价自相矛盾（job-tracker 页 Pro $30/月，interview-tracker 页 $40/月）。
- Jobscan 官网与帮助中心 403，付费档位（5 次/月、$49.95/月）仅来自联盟营销型评测站，需二次核实。
- Logseq 的 Git 版本控制未从官方一手页面核实（docs.logseq.com 为 SPA，logseq/docs 与源码路径均 404），仅见低可信度二手中文博客，报告中已标注存疑。
- 开源对比对象普遍极早期（CareerDesk 38★且仅 3 commits、OfferPilot 7★、投递台 3★），功能"存在"不等于"被验证有人用"，其设计选择只能作方向参考而非需求验证。
- Bloom 简历幻觉报告为厂商自评（虚构简历、n=106、非同行评审），数据不可当独立基准，仅其"独立复核 pass 有效"的方向与 Resume-Matcher 源码实践互相印证。
- 第四路（AI 增强与岗位发现）subagent 中途中断，该节结论主要由既有调研与本报告其他三路材料综合得出，token 成本的具体量级缺少一手数据支撑。
- 文中 star 数是检索当日（2026-09-03）的即时快照，与已公开的 `report_job_search_products.md`（2026-08-31 采集）**采集日期不同**，故两份报告对同一项目的数字略有出入（如 JobSync 本报告 974★ / 那份 967★）。**两处都不应当作当前实际值**，个位数差异也不代表趋势。

## References

1. [srbhr/Resume-Matcher（BYOK 标杆，含 ATS 评分与反编造护栏）](https://github.com/srbhr/Resume-Matcher)
2. [Resume-Matcher: apps/backend/app/services/ats.py](https://raw.githubusercontent.com/srbhr/Resume-Matcher/main/apps/backend/app/services/ats.py)
3. [Resume-Matcher: tests/unit/test_prompt_guardrails.py（反编造护栏测试）](https://raw.githubusercontent.com/srbhr/Resume-Matcher/main/apps/backend/tests/unit/test_prompt_guardrails.py)
4. [Resume-Matcher: tests/unit/test_verify_diffs.py（diff 本地校验）](https://raw.githubusercontent.com/srbhr/Resume-Matcher/main/apps/backend/tests/unit/test_verify_diffs.py)
5. [Huntr Job Application Tracker & CRM](https://huntr.co/product/job-tracker)
6. [Huntr Interview Tracker](https://huntr.co/product/interview-tracker)
7. [Simplify Job Application Tracker](https://simplify.jobs/job-application-tracker)
8. [Gsync/jobsync（974★，含 Question Bank）](https://github.com/Gsync/jobsync)
9. [GitHub Topics - job-tracker（按星标排序）](https://github.com/topics/job-tracker?o=desc&s=stars)
10. [xinhuangcs/CareerDesk（FastAPI+React 桌面端）](https://github.com/xinhuangcs/CareerDesk)
11. [offercontext/offerpilot（Offer 对比与谈薪）](https://github.com/offercontext/offerpilot)
12. [karl-cta/jobctrl（含 contacts 与 follow-up reminders）](https://github.com/karl-cta/jobctrl)
13. [JobCtrl.dev（ebarti/jobctrl，local-first 双轴模型）](https://jobctrl.dev/)
14. [mengfanfreyachan/JobApplicationTracker（投递台，24h 提醒）](https://github.com/mengfanfreyachan/JobApplicationTracker)
15. [Notion 模板 - 求职申请追踪器（面试到 Offer）](https://www.notion.com/zh-cn/templates/offer)
16. [notionchina - 使用 Notion 组织面试流程（8 阶段拆分）](https://notionchina.co/articles/1698174105244)
17. [Local-first software: You own your data, in spite of the cloud（Ink & Switch, 2019）](https://www.inkandswitch.com/essay/local-first)
18. [文件恢复 - Obsidian 中文帮助（快照存系统目录）](https://obsidian.md/zh/help/%E6%A0%B8%E5%BF%83%E6%8F%92%E4%BB%B6/%E6%96%87%E4%BB%B6%E6%81%A2%E5%A4%8D)
19. [Understanding Synchronization — Syncthing Docs](https://docs.syncthing.net/users/syncing.html)
20. [File Versioning — Syncthing Docs](https://docs.syncthing.net/users/versioning.html)
21. [Joplin readme: Importing and exporting](https://raw.githubusercontent.com/laurent22/joplin/dev/readme/apps/import_export.md)
22. [Import & Export | Anytype Docs](https://doc.anytype.io/anytype/data/import-and-export)
23. [Standard Notes: How do I create and import backups?](https://standardnotes.com/help/14/how-do-i-create-and-import-backups-of-my-standard-notes-data)
24. [rendercv/rendercv](https://github.com/rendercv/rendercv)
25. [xitanggg/open-resume](https://github.com/xitanggg/open-resume)
26. [AmruthPillai/Reactive-Resume](https://github.com/AmruthPillai/Reactive-Resume)
27. [BingyanStudio/LapisCV](https://github.com/BingyanStudio/LapisCV)
28. [The Resume Hallucination Report (Bloom)（厂商自评，慎用其数字）](https://bloomcareer.io/blog/resume-hallucination-report)
29. [Jobscan Review 2026（二手，官方站 403 未取回）](https://careery.pro/blog/resume-applications/is-jobscan-worth-it-2026)
