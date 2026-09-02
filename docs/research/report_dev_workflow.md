# 调研报告：相似项目的开发流程

- 日期：2026-09-01
- 查询类型：Breadth-first（三路 subagent 并行：迭代节奏 / 分支发布 / 需求管理与自用平衡）
- **与既有调研的关系（三层互补）**：
  - `report_job_search_products.md` = **产品功能层**（做什么功能）
  - `report_dev_setup_benchmark.md` = **工程配置层**（打包/数据目录/CI 工具）
  - 本报告 = **开发流程层**（怎么组织开发：节奏、分支、版本、需求、自用平衡）
- 公众号中文源未纳入（搜狗 SSL 故障遗留）；三路英文源已覆盖核心议题。

## 执行摘要

三路共识可提炼为三句话：**①版本由日期定义，不由功能完备度定义**（Joplin 的冻结期 + 公开日期表）；**②单人项目用 trunk-based 单主干，GitFlow 是过度工程**；**③"自用优先"的最大风险不是做得慢，是把自己当成市场**——dogfooding 擅长发现"它坏了/难用"，极不擅长发现"还有人想要吗"。针对本项目，调研给出了可直接执行的四道门判断框架与一份最小可行流程清单。

---

## 一、迭代节奏与版本规划（A 路）

### 四个案例

| 项目 | 维护规模 | 迭代周期 | 版本粒度 | 优先级决策 | 可借鉴点 |
|---|---|---|---|---|---|
| **Joplin** | laurent22 绝对核心 + 3-5 位长期贡献者 | **每季度一次**（官方"每年 3 个 major"，实际递增 minor）；开发 → **发布前 2 周冻结**（只修 bug）→ 发布窗口约 1 周，官网公布到 2027 年的日期表 | semver，minor 为主（3.6→3.7），patch 窗口内密集；旧分支仍补补丁 | 需求**先在论坛提出并被接受**才进 GitHub tracker；>50 行改动必须先讨论，否则关 PR | **用"冻结 + 预先公布日期表"给版本定硬截止——版本由日期定义** |
| **Logseq** | <10 人核心 | **不固定**：0.10.x 间隔 5 天~3 个月；另有自动 **nightly** + beta，三轨并行 | 十年停留 0.10.x，架构变更才跳 2.0（DB 版） | **完全公开 live roadmap**（logseq.io，条目挂负责人与 deadline，直链 PR） | **nightly 自己用、stable 给别人用，自用与分发拆两条轨道**；2026-04 把产品一分为二，OG 版只做安全与 Electron 升级，砍半范围换速度 |
| **Cherry Studio** | kangfenmao 主导 + 每版 20-30 位外部贡献者 | **高频滚动**：2.0.0→2.0.10 约 **3-5 天一版** | patch 级滚动，单版 40-80 个 PR；2.0 是大重构 | 无公开路线图，靠 issue/PR 流入 + 维护者判断，发布说明即 changelog | **把版本号当"时间刻度"而非"功能承诺"——攒够一批就发** |
| **Anything LLM** | Mintplex Labs 小团队 | minor **6-8 周**，patch 约 2 周 | 1.x semver，minor 装 3-5 个主题特性 + 50+ PR | 公开 roadmap 页是**占位**；真实预告写在 **release notes** 里（"agent 生成图片下一版来"） | **不维护独立路线图，在发布说明里写"下版做什么"** —— 成本最低且与已交付内容对齐 |

### 三条共识

1. **节奏 = "低频承诺 + 高频出口"。** 对外稳定版是季度级（Joplin 4 个月、AnythingLLM 6-8 周），但期间必须有高频通道承接：Joplin 预发布、Logseq nightly、Cherry 3-5 天 patch。**对单人项目：6-8 周一个 minor 节拍 + 按需 patch；超过 3 个月不发稳定版，用户就流失。**
2. **minor 是节奏单位，patch 是风险单位，major 只留给架构与数据迁移。** 桌面应用普遍长期停在 0.x/1.x（Logseq 十年 0.10）。不要用 major 号表达"功能变多"。
3. **防"发不出去"靠硬截止，防"发得太碎"靠轨道分离。** 三招：①提前公布日期表 + 冻结期（到期就发，装多少算多少）——单人项目最有效的一招；②nightly/stable 双轨，自己吃 nightly，别人拿 stable；③用流程而非意志力削减负担（未 triage 的需求不接 PR、bot 跑 changelog）。

---

## 二、分支策略与发布流程（B 路）

### 策略对比

| 策略 | 做法 | 适用规模 | 单人项目必要性 |
|---|---|---|---|
| **Trunk-based** | 只有 `main`；大改动开短命分支（≤1-2 天）后合并 | 单人/2-5 人 | **必做（底座）** |
| **GitHub Flow** | `main` + 每事一分支 → PR → merge → 删分支 | 有协作需 review | **推荐**（用其分支命名，可省 PR 自审） |
| GitFlow | `master`+`develop`+`feature`/`release`/`hotfix` | 多版本并行 + 正式 QA | **过度（明确不建议）** |
| Release 分支 | 主干外切发布支做稳定化 | 需同时维护多线上版本 | **可选/可省** |
| Hotfix 分支 | 从 tag 拉支修 bug | 有存量用户需维护旧版 | **过度（改用 fix-forward）** |
| **semver + git tag** | `vX.Y.Z`；feat→MINOR、fix→PATCH、BREAKING→MAJOR | 任何要分发的软件 | **必做** |
| Conventional Commits | `feat:`/`fix:`/`!` 前缀 | 想自动出 CHANGELOG | **推荐**（成本极低，收益后置） |
| CHANGELOG 自动生成 | semantic-release（需 CI）/ git-cliff（本地 CLI） | 前者要有 CI；后者任何人 | **可选**（0.x 手写即可） |

### 实证

- **Joplin**：默认分支 `dev`，另有 `release-3.7`、`release-3.6` 活跃 → release 分支模式（与其多端多版本规模匹配）
- **Cherry Studio**（51k star）：默认分支仅 `main`，活跃分支全是短命特性分支 → **纯 GitHub Flow**

### 两个特别问题

**0.x 要不要守 semver？要，但简化版。** semver 第 4 条明确 `0.y.z` 处于初始开发阶段、公共 API 不应视为稳定。实操：`feat`→`0.x+1.0`，`fix`→`0.x.y+1`，破坏性变更照常写进 CHANGELOG；**等"自用稳定 + 承诺本地数据向后兼容"时升 `1.0.0`**。

**CHANGELOG 自动生成？0.x 阶段手写。** Keep a Changelog 明确"changelog 是给人看的"，反对把 commit log 当 changelog。建议手写 `Unreleased` → 发布时转版本段。因为已用 Conventional Commits，随时可本地跑 `git-cliff` 补生成。**不建议 semantic-release**（依赖 CI 且接管版本号决策，而 Electron 需手动 bump 后构建）。

### Electron 发布的硬约束（事实）

- `update.electronjs.org` 免费服务硬性条件：macOS/Windows、**公开**仓库、发到 GitHub Releases、macOS 必须代码签名
- electron-builder 可自动更新的目标只有 macOS DMG、Windows **NSIS**、Linux AppImage；**macOS 未签名则自动更新不工作**
- 撤回坏版本必须**递增**到更高版本，重发同名版本无效
- **本项目"仅本地 git 不推送"意味着自动更新不可用**；若要自动更新需公开仓库（本项目含本地求职数据，公开前须确认无隐私入库）

---

## 三、需求管理与自用平衡（C 路）— **本项目核心矛盾**

### 需求管理做法

| 做法 | 典型项目 | 单人项目必要性 |
|---|---|---|
| README/VISION 写死边界与"不做什么" | opensource.guide（Slate 教训） | **必做**（防 scope creep 唯一低成本手段） |
| `config.yml` 把功能请求/求助导向讨论区，issue 只留可执行 bug | Joplin（`.github/ISSUE_TEMPLATE` 只有 BUG_REPORT + config） | **必做**（10 分钟，永久省事） |
| 最小 label 集（bug/enhancement/good first issue/wontfix） | 通用 | **推荐**（超 8 个即过度） |
| Milestone（v0.1 自用可用 / v0.2 可分发） | 通用 | **推荐**，比 Projects 轻 |
| GitHub Projects 看板 | Joplin/Logseq 级别 | **可选**；issue <50 时**过度** |
| 公开 roadmap（README 一节或自带产品发布） | Logseq（路线图用自己产品写，条目带负责人/PR/截止日期） | **推荐** |
| **插件/配置层作为长尾逃生口** | geerlingguy「只做 80% 用例，独角兽请 fork」 | **必做**（我们已有"领域插件 + personal/config"分层，正好符合） |
| 需求投票工具、roadmap 独立网站、复杂 label 体系 | — | **过度** |

### 核心：dogfooding 的能力边界（最重要的一条）

**Dogfooding 极擅长回答"它坏了吗/难用吗"（quality finding），极不擅长回答"除了我还有人想要吗"（desirability finding）。** 内部用户是有偏样本：更懂心智模型、容忍怪癖、配置是极端值（NN/g 的 false-consensus effect、"You Are Not the User"）。

结论：**自己当最严格的真实用户用，不把自己当市场。**

### 四道门判断框架（建议写进 CONTRIBUTING）

任何需求触发时依次过：

1. **第几次？**（rule of three）第一次 → 写一次性脚本/文档，**不进代码库**；第二次 → 把硬编码抽成配置项；第三次 → 才抽象成功能。（求职季的紧迫需求大多死在第一道门）
2. **含不含"我的私人事实"？**（成绩、公司名单、暖通词表、方向锚点表）→ 一律进 `personal/config` 或领域插件，**永不进核心代码**。（这条能自动过滤掉本项目 80% 的自用需求）
3. **泛化代价多少？** ≤ 约 1 小时 → 顺手做；>1 小时 → 只开 issue 记录，不为"顺手"破坏结构。
4. **会不会动数据模型或"两条红线"？** → 必须另开 issue/ADR 论证，**禁止因当前一次投递的紧迫性改动**。

**结构性保险**：每周固定留 1 条"产品化任务"（配置化/文档/测试），与自用任务分离。没有这条，自用优先必然腐化。

### 外部需求四问（任一为否立刻关闭并说明）

① 在 VISION 内吗？② 有**第二个**真实用户需要吗？③ 能否用插件/配置解决（能 → 指向扩展点）？④ 我愿意长期维护它吗？—— **"No is temporary, yes is forever"**（shykes）。不回应比拒绝更伤人。

### 单人可持续性

- **时间盒公开化**：WP-CLI 维护者 danielbachhuber 每周只投 2-5 小时；把"每周 N 小时""可能 7 天才回复"写进 README，公开承诺降低内疚型加班
- 开 issue 数上限（如 30），超出即 triage 关闭
- 宣布停工窗口（面试周/笔试周不开发）
- 提前写 VISION 与交接说明（Dokku 的 @progrium 写下愿景后即使离开，项目仍朝那个方向走）
- **让项目与自身目标同向**：本项目产出物本身就是求职资产，维护成本不是从求职时间里扣的——这是"自用优先"最大的抗 burnout 优势

---

## 四、对本项目「后续开发流程」的具体建议

### 立即可执行（最小可行流程）

**分支：`main` 单主干 + 短命特性分支**
- 日常直接提交 `main`；只在"可能放弃的实验 / 半天完不成的重构 / 会破坏当前可用状态"时开分支，完成即合即删
- **不要** `develop`、`release`、`hotfix` 分支

**版本：semver + tag，0.x 阶段**
- 版本号唯一来源 = `package.json` 的 `version`
- `feat`→`0.x+1.0`，`fix`→`0.x.y+1`；升 `1.0.0` 的时机 = "自用稳定 + 承诺本地数据向后兼容"
- 采用 Conventional Commits（成本极低，为将来自动 CHANGELOG 留口）

**发布：从 `main` 打 tag，不从分支发**
1. 本地跑通 → **打包后安装运行一次**（安装版与 dev 差异大）→ 打开旧数据验证（无测试，冒烟是唯一不可省的替代）
2. `npm version patch|minor`（自动改版本 + 建 tag）
3. CHANGELOG 的 Unreleased 段转成版本段 + ISO 日期
4. electron-builder 出安装包，产物按版本归档
5. **只在"要给外部装/需留档"时**才走 1-4；日常自用直接从源码跑

**hotfix：fix-forward**，在 `main` 上修后打新 patch tag。唯一例外：用户卡在旧版且数据不兼容时才 cherry-pick。

### 需求管理（轻量）

- 用 **Milestone** 而非 Projects（v0.1 自用可用 / v0.2 可分发）
- 最小 label 集：bug / enhancement / wontfix
- **在发布说明里写"下版做什么"**（AnythingLLM 做法，成本最低）
- 沿用已有三层分离作为长尾逃生口（tools 领域无关 / template 插件 / personal 私人事实）

### 自用与产品化平衡（本项目关键）

- 严格执行**四道门**框架，尤其第 2 道（私人事实不进核心代码）
- 每周固定留 1 条产品化任务，与自用任务分离
- README 写明：边界与"不做什么"、每周投入时长、停工窗口

### 明确不做（过度工程）

`develop`/`release`/`hotfix` 分支、CI、分支保护、PR 自审、semantic-release、GitHub Projects 看板（issue<50 时）、需求投票工具、复杂 label 体系、roadmap 独立网站、Playwright E2E、代码签名（自用阶段）。

### 关于自动更新的现实约束

本项目仅本地 git 不推送 → **自动更新不可用**，分发只能手动给安装包。若要自动更新需公开仓库，**公开前必须确认无隐私数据入库**（personal/ 含姓名/照片/成绩/投递记录）。这是未来要做产品化分发时的一个关键前置决策。

---

## 五、局限性

- 各项目"维护人数"由 release notes 署名与贡献者列表推断，非官方编制数。
- Cherry Studio 只验证了 2026-08-05 至 08-28 的 2.0.x 序列，1.x 期节奏未核。
- "避免 burnout"部分是制度性推断，未找到维护者本人的一手访谈（相关页面返回 403）。
- Dogfooding 指南（Koji）内容扎实但属厂商营销页，其引用的 NN/g、CB Insights 数据为二手转述。
- Joplin 是"单人主力 + 社区"而非纯单人，结论迁移到本项目应打折。
- trunkbaseddevelopment.com 是倡导性站点（立场鲜明，直接称 GitFlow 与之不兼容），其结论应视为带观点的实践建议。

## References

1. [Joplin Release Cycle（官方发布周期与日期表）](https://joplinapp.org/help/about/release_cycle/)
2. [Joplin Getting pre-releases](https://joplinapp.org/help/about/prereleases/)
3. [Contributing to Joplin（功能请求/PR 接受规则）](https://joplinapp.org/help/dev/)
4. [Joplin Releases Atom](https://github.com/laurent22/joplin/releases.atom)
5. [Logseq Releases Atom](https://github.com/logseq/logseq/releases.atom)
6. [Logseq Public Roadmap](https://logseq.io/p/NX4mc_ggEV)
7. [Big update: Logseq is splitting into two versions](https://logseq.io/p/e3YDyX5AYr)
8. [Cherry Studio Releases 页面](https://github.com/CherryHQ/cherry-studio/releases)
9. [AnythingLLM Releases Atom](https://github.com/Mintplex-Labs/anything-llm/releases.atom)
10. [AnythingLLM roadmap.mdx（官方路线图页）](https://raw.githubusercontent.com/Mintplex-Labs/anythingllm-docs/main/pages/roadmap.mdx)
11. [Introduction - Trunk Based Development](https://trunkbaseddevelopment.com/)
12. [Alternative branching models - Trunk Based Development](https://trunkbaseddevelopment.com/alternative-branching-models/)
13. [GitHub flow - GitHub Docs](https://docs.github.com/en/get-started/using-github/github-flow)
14. [语义化版本 2.0.0（中文）](https://semver.org/lang/zh-CN/)
15. [Conventional Commits v1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
16. [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/)
17. [Publishing and Updating | Electron](https://www.electronjs.org/docs/latest/tutorial/tutorial-publishing-updating)
18. [Auto Update | electron-builder](https://www.electron.build/docs/features/auto-update/)
19. [Branches · laurent22/joplin](https://github.com/laurent22/joplin/branches)
20. [Branches · CherryHQ/cherry-studio](https://github.com/CherryHQ/cherry-studio/branches)
21. [GitHub - orhun/git-cliff](https://github.com/orhun/git-cliff)
22. [Open Source Guides - Best Practices for Maintainers](https://opensource.guide/best-practices/)
23. [joplin/.github/ISSUE_TEMPLATE](https://github.com/laurent22/joplin/tree/dev/.github/ISSUE_TEMPLATE)
24. [Logseq Product Roadmap - Announcements](https://discuss.logseq.com/t/logseq-product-roadmap/34267)
25. [Product Dogfooding: A Complete Guide (And Where It Falls Short) - Koji](https://www.koji.so/docs/product-dogfooding-guide)
26. [保持开源维护者的平衡 | Open Source Guides](https://opensource.guide/zh-hans/maintaining-balance-for-open-source-maintainers/)
