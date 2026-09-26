# 贡献与开发流程（完整版）

> **本文是完整的中文细则，也是唯一权威版本。** 短索引在仓库根 [CONTRIBUTING.md](../CONTRIBUTING.md)
> （英文，对齐 README 的 English-first）；英文伴读版为 [contributing.en-US.md](contributing.en-US.md)
> ——按**两档承诺**维护：**必读节**（项目定位 / 隐私约定 / 新需求四道门 / 分支策略 / 提交规范 /
> 四端一致性 / 文案与 i18n / 代码卫生 / 明确不做 / 可持续性约定）**承诺与本文同步**；
> **治理节**（版本号体系 / CHANGELOG 写法 / 发布流程 / 发布治理 / AI 协作者 / 开发者工具）
> **只承诺摘要**。决策史、日期证据与案例记录只存在于本文；**任何冲突以本文为准**。

本文定义本仓库的开发流程约束。适用对象：维护者本人（第一用户）、AI 协作者与外部贡献者。
数据分层与领域约定见 [AGENTS.md](../AGENTS.md)；文档索引见 [docs/README.md](README.md)。

## 项目定位（先读这个）

- **自用优先**：维护者是第一用户。把项目当最严格的真实用户去用，但**不把自己当市场**——dogfooding 能回答"它坏了吗 / 难用吗"，不能回答"有人想要吗"。
- **单人维护**：流程以"最小可行"为纲。凡是维护成本超过收益的工程化设施，一律不做（见文末"明确不做"）。
- **仅本地 git**：曾长期无远程与 CI；开源后以 GitHub Actions 跑测试与构建作为质量门，分发仍以手动归档安装包为主。

## 隐私约定（开源后生效，贡献前必读）

- **本仓库不含真实个人数据**：`personal/` 已整体加入 `.gitignore`，历史中的真实数据也已清洗。
- **禁止提交任何 `personal/` 内容**：包括其中的文件路径、真实公司名、简历片段、投递记录、截图。
- **禁止提交真实身份信息**：姓名、电话、邮箱、学校、证件号、照片——文档与示例中一律使用占位（`示例公司A`、`sample@example.com`、`你的姓名`）。
- **示例用假数据**：测试与模板沿用既有假数据（`13800000000`、`z@x.com`、`示例公司A`），不要替换成真实信息。
- **发现泄露怎么办**：直接开**公开 issue 只报位置**（**不要贴出泄露内容本身**），维护者会用 `git filter-repo` 清洗历史。
- **两条通道，别混**：**隐私数据泄漏**（某份真实文件进了历史）走上一条——公开 issue **只报位置**；**可被利用的安全漏洞**走 [SECURITY.md](../SECURITY.md) 的私密通道（Security → Advisories），公开 issue 里不写复现细节（那会先把所有用户置于风险中）。

## 新需求四道门（每次动手前依次过）

任何新需求——不管来自自己的使用痛点还是他人建议——先过这四道门：

1. **这是第几次？**（rule of three）
   第一次 → 写一次性脚本或文档，**不进代码库**；第二次 → 把硬编码抽成配置项；第三次 → 才抽象成通用功能。
2. **含不含个人事实？**
   任何只属于"某个人"的信息（个人事实文件的内容、个人词表、个人清单）→ 一律进 `personal/` 配置层或领域插件，**永不进核心代码**。这条能过滤掉大部分自用需求。
3. **泛化代价多少？**
   ≤ 1 小时 → 顺手做；> 1 小时 → 只开 issue 记录，不为"顺手"破坏结构。
4. **动不动数据模型或诚实红线？**
   涉及数据格式变更、或触碰 [AGENTS.md](../AGENTS.md) 的诚实红线 → 必须另开 issue/设计说明论证，**禁止因一次使用场景的紧迫性直接改**。

**结构性保险**：每周固定留 1 条"产品化任务"（配置化 / 文档 / 测试），与自用任务分开推进。没有这条，自用优先会让产品化无限延后。

## 分支策略（分级 PR + trunk-based）

- `main` 是唯一主干。按**改动是否影响运行时行为**分级，不搞一刀切：

**必须走 PR**（影响运行时行为的改动）：

- `tools/`、`web/backend/`、`web/frontend/` 的代码修改，`tests/` 用例
- 依赖变更（`requirements*.txt` / `package.json`）；CI / workflows 配置
- 数据模型 / schema 变更；触碰 [AGENTS.md](../AGENTS.md) 诚实红线的内容
- PR 门槛：CI 绿（后端 pytest、前端 lint + build、PR 标题校验、UI 冒烟**四个 check 全过**——**PR 合并前的流程硬要求，红不许合**）+ 对照 [PR 模板](../.github/PULL_REQUEST_TEMPLATE.md) 自查 + **双轨审查（两轮均可定位，借鉴 branch closeout 的 Review Intake 条款）**：
  1. **作者自审**：逐文件通读 `gh pr diff`（重点：隐私与四道门、API 消费面、改动是否纯增量），结论用 `gh pr comment` 落进 PR；
  2. **独立审查**：派一个**全新上下文**的子代理以陌生 reviewer 视角逐文件审同一 diff（不带入作者意图，只看代码本身）；
  两轮结论（含发现的问题与处理决定）都必须留在 PR 页面——单人开发也要让 PR 可追溯「改了什么、两轮各审出了什么、为什么这么定」；**不得将作者自审标称为独立审查，不得伪造审查身份**；独立审发现 MAJOR 级及以上问题当场修（追加 commit）或记入后续 PR，不许静默合并（实证：PR #13 独立审抓出自审完全漏掉的 3 个 MAJOR）；Squash and merge，合后删分支

> **跨宿主复现（2026-09-14 起）**：第二轨不绑宿主——`python scripts/review.py`（默认自动探测第二个 CLI：claude / codex）会先把 `base...head` 的完整 diff 落到根目录（`tmp_review_diff.patch`，已 gitignore），再让审查方**自己读文件**产出 findings——大 diff 不会被入参上限截断；同一套提示词在 CodeBuddy 子代理、Claude Code、Codex 上通用。实测：对已合 PR 的跨宿主复核可与子代理轨的结论对照使用。
>
> **例外（机器人依赖 PR，2026-09-13 定）**：由 GitHub 官方 Dependabot 创建的依赖升级 PR（判据：作者为 `dependabot[bot]` **且**带 `dependencies` 标签——不只看作者名，作者名是外部可控字段），**仍需作者自审**，仅豁免第二轮独立审查；门槛 = 作者自审 + 四项 CI。
> - 理由：这类 PR 的 diff 是版本号与锁文件，第二轮评审的信息量极低；真正的验证者是 CI（构建、测试、UI 冒烟），而把「两轮」套在它上面只会催生走过场。
> - **边界（三条，缺一不可）**：① 只覆盖 **patch / minor** 升级；**major 升级不适用**（例：electron 33 → 44 是 11 个 major，必须走人工批次并做运行时/桌面冒烟——调研见 `docs/research/report_electron_33_to_44.md`）。判据：**以依赖包自身的 semver 主版本号是否变化为准**（版本号的首段不同即 major），不看 PR 标题措辞、也不看依赖类型（dev/prod 一视同仁）。② 仍须**改中文标题**（闸门照旧，机器人开不出合规标题）。③ 自审评论必须写明「改了什么 + 兼容性判断」，不能只写「CI 绿了」。
> - 与 §提交规范 的关系：豁免的是**审查轮次**，不是标题语言规则——两条不要混。
> - 换机器人（如 Renovate）或作者名不匹配时，本例外**不适用**（回到两轮要求）——失效方向偏保守。

**所有改动都走 PR**（含纯文本与资料类）：`main` 启用了分支保护且 `enforce_admins` 开启——直推在物理上会被拒绝；CI 的必需检查（后端测试 / 前端构建 / PR 标题 / UI 冒烟）全绿才可合入。历史注记：保护启用（2026-09-08）前曾允许纯文本直推；该口径已作废（2026-09-25 订正——`enforce_admins=true` 下直推从来不是可执行的选项）。

- **先开分支，再动手**：分支要在敲第一行代码前建好（`git switch -c feat/xxx`），不要先在 `main` 写完再 checkout——那样虽然未提交改动会被带到新分支、`main` 仍干净，但流程易混淆，一旦中途忘记开分支，提交就直接落进 `main`。
- **本地提交护栏（githooks）**：克隆后执行 `git config core.hooksPath .githooks` 启用。pre-commit：隐私护栏（`personal/` 路径与真实手机/邮箱模式在提交入口直接拦截）+ >1MB 文件检查 + **规模预算（与 `jobws lint size` 同源实现，只扫暂存文件；存量见 `tools/size_allowlist.txt`）** + pytest 快检（全量 **≈25s**（2026-09-20 实测 934 条）；超 60s 会在输出里点名阈值，见下「测试规模与阈值」；解释器缺 pytest 时降级为提示，CI 兜底）；commit-msg：Conventional 格式 `type(scope): subject`（type 限定枚举、**subject 必须含中文**、≤100 字符），豁免 Merge/Revert。判定逻辑在 `tools/commit_header.py`，与 CI 的 PR 标题校验同源。紧急跳过 `--no-verify`（用了要在 PR 里说明原因）。
- **PR 标题也被校验（CI workflow `pr-title`）**：本地钩子只在你自己敲 `git commit` 时运行，而 PR 标题是 GitHub 在合并时用来生成提交 subject 的，**本地钩子结构上看不到它**——这一步只能由 CI 做（语言规则见 §提交规范）。`tools/jobws.py lint pr-title` 经 `PR_TITLE` 环境变量取标题，不拼进 `run:`：PR 标题是外部可控输入，拼进 shell 等于开后门。违规时 CI 红，`gh pr edit <编号> --title "feat(scope): 中文说明"` 即可——这个 workflow 单独一份并显式订阅了 `edited`，因为 `pull_request` 默认只触发 opened / synchronize / reopened，**改标题默认不会重跑**，那样「按提示改标题」就清不掉红叉（2026-09-10 实测踩到）。
- **开 PR 前先本地预检标题（同一套实现，一秒钟省一轮返工）**：`python tools/jobws.py lint pr-title --title "<你准备用的标题>"`。CI 才是硬闸，但本地预检能把「开完 PR 才发现标题违规」提前到按下回车之前（2026-09-12 实测：scope 写成 `feat(api,ui)`——scope 正则不含逗号，本地两笔提交都合规、PR 标题到 CI 才红）。
- **PR 的粒度是「一个可独立验收的批次」，不是「一次提交」**：分支内可以多次小步提交，全部完成且 `npm run build` / 测试绿之后再开一次 PR。例：P1 的三批页面迁移 = 三个 PR。
- 分支命名（PR 路径）：`feat/<issue号>-<slug>`、`fix/<issue号>-<slug>`、`docs/<slug>`；存活 ≤ 1–2 天，合完即删。
- 兜底（出错了怎么办）：数据快照备份 + `git revert`——squash 提交可整体回滚，不污染主干历史。
- 分支也是这三种情况的隔离手段（与上一条不冲突——所有改动都走 PR，这里说的是该开什么样的分支）：可能放弃的实验 / 半天以上完不成的重构 / 会临时破坏"当前可用状态"的改动。
- **不设** `develop` / `release` / `hotfix` 分支。

## 提交规范（Conventional Commits）

格式：`<type>(<scope>): <描述>`

- `feat` / `fix` / `docs` / `chore` / `refactor` / `data` / `job`：**都不触发版本号变化**——版本号按发布当月（月粒度 CalVer `YY.MM.N`）生成（见 §版本号体系），不再由提交类型推导。
- 破坏性变更：`!` 后缀或正文 `BREAKING CHANGE:` 段；落地时写进该版 CHANGELOG 的「破坏性变更」小节（版本号本身不再表达破坏性）。
- **数据操作与代码分开提交**：往工作区录入数据的提交用 `data:` / `job:` 前缀，不与功能提交混合
- **语言：提交 subject 与 PR 标题一律中文，正文也用中文**（机器判定，不是风格偏好）。**不写中文的外部贡献者**：照开 PR 并在正文说明即可——本地 `commit-msg` 钩子会拒绝（用 `--no-verify` 提交并注明），CI 的 PR 标题闸也会红，两者都属预期；**维护者在合并前替其改名**（不要求对方去和机器人搏斗）。PR 标题在 squash 合并后会**直接成为主干上的提交 subject**，所以这两处是同一条规则的两半——只约定提交信息而漏掉 PR 标题，就会出现「作者本地提交是中文、合并进主干却变成英文」的混排（实证：PR #15 / #16 的英文标题以 `53e7b04` / `b774cce` 落进 main，夹在前后中文提交之间）。subject 与标题由钩子 + CI 机检（见 §提交流程）；**PR 正文不机检**——正文里必然有代码块、type 枚举与英文术语，机器判定只会做出一个被绕过或被抱怨的噪音闸，这部分靠双轨审查。issue / PR 模板里的英文表头是给外部反馈者的**填空提示**，不是正文语言要求；面向英文读者的 README / docs 英文版另论。
- **合并方式**：`main` 开了 `required_linear_history`，所以只有 squash 与 rebase 两条路。**用 squash**——rebase 会把分支里每条提交的原始 subject 原样铺进主干，PR 标题那道闸就完全绕过了（本地 commit-msg 闸此时是唯一拦截点）。
- **合完就删分支（两侧都删），别攒着**。2026-09-16 清账时发现本地积了 **26 个已合并分支**（远端也留着 8 个），根因是 squash 的副作用——**squash 会重写提交，分支与 `main` 的 ancestry 永远对不上**，于是 `git branch --merged main` 一个都认不出来，`git branch -d` 也会拒绝，看起来像「这些分支还有用」。实际上它们全部对应已合并的 PR。
  - **判据只有一条可信：PR 记录**（`merged: true`），不是 `--merged`、也不是 `git rev-list main..<branch>`。清账脚本 `tools/branch_audit.py` 走的就是这条（按分支名查 PR → 读 `merged`；无 PR 时才回退到「头部 subject 是否已在 main」）。**只报告、不删除**——它打印「可安全删除 / 需人工确认 / 保留」三组，删的动作由人决定：
    ```bash
    python tools/branch_audit.py          # 先看报告
    git branch -D <branch> [...]          # 确认后再删
    ```
  - **远端**：仓库已开 `delete_branch_on_merge`，合并时自动删。手动补删用 `git push origin --delete <branch>`。
  - **本地**：合并后 `git branch -D <branch>`（`-D` 而非 `-d`——如上，`-d` 在 squash 场景下必然误判为「未合并」）。
- **这道闸拦不到的两条路（已知缺口，别把它当万能）**：
    1. **在 squash 对话框里手动改掉最终的提交信息**：那既不改 PR 标题、也不触发 `edited`，校验不会重跑——英文 subject 照样落进 main。机制上拦不住（`pull_request` 事件看不到你合并时手填的那段），所以规矩是**合的时候不要动默认的提交信息**。
    2. **校验脚本与被校验对象同源同 PR**：workflow 与 `tools/*.py` 都取自 PR 自己的分支，所以一个 PR 可以顺手把判定放宽（把 CJK 正则改成 `.*`）而 CI 依旧全绿。单人仓库没有第二个审批人，实际防线是 `tests/` 里钉住的行为——放宽正则会让那批用例立刻红。**改判定规则时必须同步改测试并写明理由**，这就是这条防线起作用的唯一方式。

## 版本号体系（月粒度 CalVer `YY.MM.N`，2026-09-24 起）

语义化版本号已弃用（0.x 的 minor/patch 映射、`v1.0.0` 的提法一并作废）。现行规则：

- **单一形态（2026-09-24 起）**：版本号 = **月粒度 CalVer `YY.MM.N`**（如 `26.9.0`）——tag、CHANGELOG 段名、`web/electron/package.json` 的 `version`、`latest.yml`、产物文件名、界面「关于」区块**全部是同一个号**（不再区分「发布号 / 机器版本」双形态）。
- **第三位 `N` = 当月第几发**（从 0 起）：首发 `26.9.0`；hotfix **锁前两位只动第三位**（`26.9.1`——这是 electron-updater 语义下唯一能触发更新的 bump 方式：`-rc` 后缀会被判更旧、`+N` 后缀参与判等，都不触发）；同月第二发继续递增（`26.9.2`）；换月清零（`26.10.0`）。
- **为什么必须改（实测证据）**：electron-updater 的版本比较直接走 Node semver——四段（`26.9.15.1`）与月份补零（`26.09`）都**非法**（`semver.valid` → null，比较抛 `TypeError` 或直接 skip tag），旧双形态随之一并作废；月粒度三段是合法 semver，且有 Bitwarden Desktop（`YYYY.N.P`）同类先例。
- **生成**：`python tools/jobws.py release version` 打印"若本月发布"的号（读 `git tag` 序列，当月已有 tag 时 N 递增，不落状态文件）。**写入 `package.json` 仍由人工 bump**（发布流程第 2 步），`release check` 把关。
- **唯一来源**：`web/electron/package.json` 的 `version`；不存在第二套真值源。
- **tag 约定**：`v<版本号>`（如 `v26.9.0`）；**CHANGELOG 段名 = 版本号**。tag 与版本的比对规则 = **逐字相等**（`release_assist.version_matches_tag`，本地与 CI 同源）。
- **破坏性变更**：不再由版本号承载——写进该版 CHANGELOG 的「破坏性变更」小节 + 段首「升级须知」（影响与迁移步骤）。
- **发布纪律（2026-09-15 起）**：**单一发布节点**——中间批次不 bump / 不 tag / 不 Release / 不出安装包；全部批次做完后只发布一次。
- **其它 version 字段（私有 / 独立包，不参与发布）**：`web/frontend/package.json` 与 `mcp/pyproject.toml` 的 `version` 是各自包的私有字段，**不得与发布号联动**；`.codebuddy-plugin/marketplace.json` 无 version 字段。**例外（派生物，不是真值源）**：领域包 `packages/jobws-core` 的版本在**构建期**由它自己的 `setup.py` 读 `web/electron/package.json` 写进 wheel 元数据，运行时从 `importlib.metadata` 读回（CI 断言三者一致，见 `jobws_core/_version.py`）。它同样**不是**真值源——改版本仍然只改 `package.json` 一处，不要去改包的 `pyproject.toml`。
- **当代参考**：tag 序列从 `v0.1.0`（2026-09-08）到 `v0.3.2`（2026-09-14）为语义化时代，`v26.09.15.1` 时期（2026-09-15 体系，**未真正发布过 tag**）作废；**下一个版本是 `26.9.0`**（2026-09 月粒度首号），实际值一律以 `web/electron/package.json` 与 `git tag` 为准。

## CHANGELOG 写法（单文件两级制，2026-09-20 起）

对外发布时 CHANGELOG 是读者的第一站，写法按「写给人读」约束（Keep a Changelog 的落地方案，参考了 Tailwind / Ant Design 等项目的实际形态）：

- **每个版本段两级**：段顶先写 `### Highlights (English)`（3–5 行英文摘要——**英文只承诺摘要，不承诺逐条**）与 `### 看得见的变化`（中文白话 3–5 条：动词开头、一条一事、行尾挂 PR / issue 号）；下面用 `### 技术细节` 收原始详注（历史原文不改）。
- **内部工程条目只进 `Infrastructure` 节**（CI / 测试 / 水位 / 重构 / 包化 / 脚本 / 文档校对），该节首行保持「不影响使用、是内部质量改进」的固定导语；判据 = **是否改变分发形态软件的用户可见行为**。
- **术语不许裸奔**：新出现的内部术语要么在条目里当场一句话解释，要么收进 `docs/glossary.md` 并从条目链接过去。
- **版本段要自洽**：段内按日期倒序；底部 compare 引用补齐（指向真实 tag）；`[Unreleased]` 是发布前的累积区，发布时改为发布号 + ISO 日期（见 §发布流程）。
- **历史段保持原样**（0.3.2 及以前）：只加一行「本节为原始详注，格式自下版起统一」的注记，不回填。

## 发布流程（手动归档）

从 `main` 打 tag，不从分支发（**单一发布节点**：中间不发布，见 §版本号体系）：

1. **冒烟验证**（CI 已跑全量自动化测试，人工冒烟不可省）：跑构建脚本产出安装产物 → **安装运行一次** → 用旧数据打开八个页面各操作一遍；UI 相关批按截图对比验收（能指出可见差异）。
2. **生成当月号并 bump 版本**：`python tools/jobws.py release version` 取"本月发布号"（`YY.MM.N`）→ 把 `web/electron/package.json` 的 `version` 写为同一个号。
3. 把 [CHANGELOG.md](../CHANGELOG.md) 的 `Unreleased` 段改为**版本号** + ISO 日期（段名与 tag 同名）。
4. **打 tag 前本地预检**：`python tools/jobws.py release check --tag v26.9.0`——校验 tag 与版本**逐字相等**、CHANGELOG 有该版本段，并预览将发布的 Release 说明（与 CI 同一实现；红着就别打 tag）。
5. **dry_run 演练**：`gh workflow run release.yml -f dry_run=true -f tag=v<版本号>`（产出 exe + `latest.yml` 与说明，不碰 Release；`tag` 输入用于校验 CHANGELOG 段与版本比对——**需在第 3 步落章之后跑**）→ 通过后再 `git tag -a v<版本号> -m "..."` 并推送。
6. 发布后核验 `gh release view --json assets`（安装包 + `latest.yml` 都在）并**真下载一次**；构建产物按发布号归档到仓库外目录（产物已被 .gitignore 排除）。

**hotfix**：fix-forward——开 `fix/` 分支走 PR 合入 `main`，再取当月号发布（**锁前两位只动第三位**，N 递增；换月重新从 0 起）。**不**从旧 tag 拉 hotfix 分支。
**撤回坏版本**：用**更高**版本号重发（当月 N 递增即可）；重发同名版本无效——electron-updater 不会接受相同或更低的号覆盖（详见 `docs/release-checklist.md` 的 RUNBOOK）。

**自动更新**：Windows 打包版**已启用**（electron-updater，v0.2.1 起；unsigned 更新链的取舍已记于 SECURITY.md），首次分发仍走手动安装包；**macOS 自动更新不做**（剩余阻碍是代码签名，系统必需）。`personal/` 隐私剥离已完成（整体 gitignore + `git filter-repo` 历史清洗）。

## 发布治理（阻断清单 / 窗口纪律 / 分层验证）

**发布阻断清单**——满足**任一**即不得正式发布（与普通 P1/P2 分开对待，这八类没有"下个批次再修"的选项）：

1. 数据损坏或静默覆盖；
2. secret / 凭据泄漏；
3. 路径越界类安全问题；
4. installer 无法安装或启动；
5. 更新链失效（`latest.yml` / 自动更新路径断）；
6. 主流程阻断（打开即崩、核心页不可用）；
7. privacy 文案与真实行为不一致（`docs/data-flow-matrix.md` 是权威底稿）；
8. backup / restore 不可靠——"能生成 zip"不算，restore 验证过才算。

其中**四类不等待功能批次**，可直接走 `26.9.N` hotfix（ADR `ship-once-per-release` 的 2026-09-25 补充）：**安全漏洞 / 数据损坏·静默覆盖 / 安装·启动阻断 / 更新链失效**。

**发布窗口纪律（RC 阶段）**：从发布意向确定（取号 / 落章）到 tag 之间为**功能冻结期**——`main` 只接发布阻断类修复，其余改动排队到下一个 `N`。窗口标准动作：dry_run 演练（release.yml 全链，含强制全量 E2E）→ 真机冒烟（`docs/release-checklist.md` 第二节）→ tag。**不实际发布 rc tag**，但窗口纪律照此执行。

**分层验证（Tier 1/2/3）**——验证责任随层级加深：

- **Tier 1（每个 PR）**：pytest 全量 + 七扫描器 + 前端 lint / tsc / 单测 + UI 冒烟（smoke / viewports / a11y / nav）；
- **Tier 2（合入 main 后）**：全量 115 条 E2E（`e2e-full` job 自动跑）+ 领域包独立安装冒烟 + exe 冒烟；
- **Tier 3（发布时）**：release.yml 全链——强制全量 E2E、安装 / 卸载冒烟、SHA256、真机人工冒烟。

**出网能力更新纪律**：新增任何联网功能，**先**更新 `docs/data-flow-matrix.md`（并同步界面隐私文案），**再**改代码——评审时未更新矩阵的出网 PR 应被拒绝（见矩阵的「治理规则」节）。

## 可持续性约定

- **时间盒公开化**：在 README 写明**投入形态**（分批——可能集中几天推进一批、也可能整周无动作；停工窗口见下）与**响应目标**（issue 首复 48 小时、滑期公示，见 `docs/maintenance.md`）；**不写吞吐量数字**——PR 数量随工具与批次波动，不是稳定承诺（2026-09-20 修正）。
- **停工窗口**：面试周 / 笔试周不开发——项目为求职服务，不是求职的对立面。
- **issue 上限**：未处理 issue 超 30 个即 triage 关闭，防积压瘫痪。
- **愿景先行**：重大方向先写设计说明（`docs/specs/`），人可以离开，愿景让项目继续走。

## 对 AI 协作者

- 本文件与 [AGENTS.md](../AGENTS.md) 是互补关系：这里管"流程"，AGENTS.md 管"数据分层与诚实红线"，互不重复。
- AI 修改代码时同样受四道门约束；发现走不到第三道门的需求，应建议降级为一次性脚本或 `personal/` 配置。
- 提交前跑通验证（脚本 / lint / tsc），不把"应该能跑"写进提交信息。
- **本地验证链（与 CI 同款）**：`pip install -r web/backend/requirements-dev.txt` → `python -m pytest tests/ -q`（**≈42s / 1455 条 —— 这是最近一次复核的当前值**（2026-09-25：1455 通过 + 14 跳过；另有 mcp 侧 60 条在 `mcp/tests/` 单独跑）；看用例数是不是被意外收集漏了）→ **提交前跑 `python tools/jobws.py lint {i18n,ui-tokens,themes,four-ends,size}`**（前三条 CI 已跑；`size` 是 2026-09-16 新增的规模预算闸门——超限先拆或登记进 `tools/size_allowlist.txt` 写清理由，别静默绕过；`four-ends` 是 2026-09-17 新增的四端一致性闸门，见下条）→ 前端 `npm run lint` + `npm run build`（Windows 用 `npm.cmd`）→ **改了纯逻辑（类名合并、格式化、回退分支）就把用例加进 `web/frontend/tests/unit/`**（`npm run test:unit`，Vitest；它刻意不引 jsdom、只收 `tests/unit/**`）→ **UI 改动加跑 `npm run test:ui`**（布局 + a11y 冒烟；需先 `npm run build` 产出 dist，且 demo 工作区存在：`python tools/jobws.py init --target demo --demo`）。
- **测试规模与阈值（2026-09-20 起）**：三套测试**分别**计阈值，别只盯 pytest 总量（增速最快的其实是 e2e）。
  - 基线（2026-09-24 实测）：pytest **97 文件 / 1352 条（+10 跳过）/ 本机全量 ≈40s**（CI 里 pytest job 约 40s，**不在关键路径**）；vitest **22 文件 / 172 用例**（`web/frontend/tests/unit/`）；Playwright **17 spec / 115 用例**（**2026-09-25 拆级**：PR 上的 `ui-smoke` 只跑最小集 smoke + viewports + a11y + nav（`npm run test:ui:smoke`），全量 115 条在 push main 后的 `e2e-full` job 跑——不阻塞 PR、合并后即回归）；MCP **7 文件 / 61 条**（`mcp/tests/`，与 pytest 分开跑）。CI 各 job 的**耗时**数量级（会随用例数浮动，看 Actions 上的当次数字）：UI 冒烟（PR 最小集）~100s / **e2e-full（main push）~170s** / 后端 exe 冒烟 ~90s / 前端构建 ~30s / MCP ~24s / 领域包 ~14s。
  - **这些数字随批次变动**：上面几个是**实测快照**不是契约，改完代码以本地实跑为准；发现与文档差得远就顺手改这里（别把"应该跑多少条"写进去）。
  - 动手阈值：**本机全量 > 60s 或钩子体感 > 30s → 先给钩子/本地加 pytest-xdist（`-n 4`，覆盖率不降；32 核机器别 `auto`）**；CI 的 pytest job > 3 分钟 → CI 侧再并行；**CI 总时长 > 5 分钟 → 先审 e2e-full 与后端 exe 冒烟（当前 ~170s / ~90s；PR 上的 ui-smoke 拆级后约 100s），不是 pytest**；> 10 分钟才谈分片/过滤。
  - 明确不做：① 钩子改跑「与改动相关的子集」——本仓库跨层耦合（领域层 → CLI → 后端 → 前端）、没有 模块→测试 映射，漏跑就是假绿；② UI 冒烟按路径过滤——有后端改动打红 UI 的先例；**2026-09-25 按「拆 job」落实**（PR 跑最小集、全量进 main push 的 `e2e-full`），不再压 `--shard`。
  - xdist 前置：`web/backend/requirements-dev.txt` 新增依赖（照常走 PR，CI 同步装）；先验并行安全（测试里的 `file_lock` 与 `pathres.snapshot_root()` 须落在 tmp）。
- **开发前先装领域包（2026-09-17 起）**：`uv pip install --python <3.12 解释器> packages/jobws-core`（venv 由 uv 创建时通常不带 pip，用 `<解释器> -m pip install packages/jobws-core` 也行）。不装也能跑——旧路径 shim 会退化到源码形态（把 `packages/jobws-core/src` 加进 `sys.path`）——但那不是目标形态：目标是**装上就能用**，CI 另有非 editable 的安装冒烟守着这条。**打包必须用非 editable 安装**（`scripts/build_backend_exe.ps1` 会拦）。
  - **往包里搬新模块时**：非 editable 安装的静态模块映射对**新增文件**不可见，不重装就会 `ModuleNotFoundError`（2026-09-19 A-1 实测）。本机开发建议 `uv pip install -e packages/jobws-core --config-settings editable_mode=compat`——compat 模式把 `src` 整体入 path，之后新增模块自动可见。
- **`jobws lint legacy-imports`（2026-09-17 新增）**：统计旧名 import 点的数量，以清单（`tools/legacy_imports_allowlist.txt`）为**只许下降**的水位。新增代码一律用 `jobws_core`；**水位降到 0 就删 shim**——`filelock` / `workspace_io` 已于 2026-09-19 走完（18 处改新名 + 两个 shim 文件删除）；`tracker` / `approval` / `pathres` 是第二批搬包后新登记的水位（PR-B 继续压到 0）。名字清完后仍留在 `LEGACY_NAMES` 里当**防火墙**：将来谁再写旧名会被当场拦下，而不是静默多出一条老路径。
- **解释器基线 3.12（2026-09-14 起，原先 3.8）**：CI、打包与文档都以 3.12 为准。技术要求其实只有 ≥3.9（`imaplib` 的 `timeout=`），但**支持**并验证的只有 3.12——所以 `tests/conftest.py` 会在收集前拦住更低版本：测试在错解释器上**静默不可信**，那种失败看起来像"代码坏了"。本题机器最常见的坑是 `python` 落到别的项目在用的 conda 环境（3.8），所以跑之前先 `python -V` 确认。
  - **pre-commit 快检的解释器**：钩子按 `JOBWS_PYTHON` > 仓库内 `.venv` > 运行钩子的解释器 解析；解析到的低于 3.12 时它**降级提示而不是拦提交**（那种结论不可信，CI 兜底）。维护者建议设一次：`setx JOBWS_PYTHON "<3.12 的 python>"`。
  - **`web/start.ps1` 用同一顺序解析后端解释器**（并额外验依赖：能 `import fastapi, uvicorn` 才算数），**不依赖终端里激活了哪个环境**——终端自动激活 conda base（或其他项目环境）时不再影响本仓库的启动；`.\start.ps1 -CheckOnly` 只做预检并打印会选哪个解释器。**`setx` 保存的用户级 `JOBWS_PYTHON` 也会被读到**（`setx` 只对新终端生效，脚本替你把"刚设完但终端还没刷新"这一步接住，并打印一行提示）。
  - **环境约定**：用一个 3.12 venv 装 `web/backend/requirements-dev.txt`。**放在仓库内
    `.venv/` 或仓库外都可以**（两者都在 `.gitignore` 里；钩子与 `start.ps1` 都优先找
    仓库内 `.venv`，放这里最省事）。实测体积约 98MB——不影响 git（已忽略），但会让
    Windows 上的**全量测试从 12s 涨到 216s**（2026-09-14 实测：文件扫描器会遍历
    `site-packages`）。**若嫌慢就放仓库外**，用 `JOBWS_PYTHON` 指过去；
    **不改动 conda 与系统 Python**（它们是别的项目的家），也不装全局 pip 包。
  - **依赖上限已在 2026-09-16 放宽**（3.8 时代钉的，基线升 3.12 后逐步解除）：现为
    `fastapi<0.142` / `pydantic<2.14` / `pypdf>=6.18.1`（`uvicorn<0.53` 未动）。放宽不是
    一次性动作而是**逐条实测**——每条都装上新版跑全量回归才合（PR #109 / #127 / #129）。
    实测口径：`fastapi 0.141.1` + `starlette 1.6.0` + `pydantic 2.13.5` + `pypdf 6.19.0`
    下 679 项全过（2026-09-16 当时的用例数，现为 934 条）；**跨 starlette 大版本（0.46→1.6）无碍**。
    仍被卡住的两条（**major，需先排迁移批次**）：`@vitejs/plugin-react` 6.x 要 `vite ^8`
    （仓库 vite 6.4.3）、`typescript` 7.x 不被 typescript-eslint 支持（`npm run lint` 直接
    失败）。两条都在 `.github/dependabot.yml` 记了到期条件，且**刻意不加 ignore**。
  - **改依赖后必须跑到 `npm run lint` / `tsc` / `vite build`**：`npm install` 退出 0
    **不代表可用**——typescript 7 那条安装成功但 eslint 运行时主动抛错。只跑安装会得出
    错误结论。

## 开发辅助工具（MCP / 代码图谱，开发者与 AI 用，非产品）

项目区分**产品运行时依赖**（终端用户跑起来需要：浏览器 + Chrome + `tools/` 脚本 + Web 层）
与**开发辅助**（开发者在写代码时借力的工具：GitNexus 影响面分析、CodeGraph 代码图、
Playwright 点页面验证）。前者在仓库里、随项目交付；后者是**开发者个人环境**的工具，
不进产品链路。因此"CONTRIBUTING 提到 GitNexus/Playwright"与"产品不含它们"不矛盾。

若要在本仓库开发时用上代码图谱工具，索引是**按仓库生成**的运行时产物，已被 `.gitignore`
排除（`.gitnexus/`、`.codegraph/`），clone / 换机后跑一次重建：

```
powershell -ExecutionPolicy Bypass -File scripts/index_dev_tools.ps1
```

前提是全局装好 `gitnexus` 与 `@colbymchenry/codegraph`（`npm i -g ...`）。MCP 声明样板见
`.codebuddy/mcp.example.json`——复制到用户级 `~/.codebuddy/mcp.json` 并替换其中的路径占位符。

**隐私提醒**：`personal/` 已随开源清洗出仓库，但本机工作区 `personal/` 仍是真实数据（简历、联系方式）。代码图谱索引会把部分文件名/符号
记进 `.gitnexus/`/`.codegraph/`（本机缓存）。这两个目录已 gitignore 不会进仓库，但**别把它们
本体外发**；索引进展用 `gitnexus list`、`codegraph status` 查看。

注意：产品侧 PR 上**不做全量** Playwright E2E（只跑最小 UI 冒烟，钉布局与 serious/critical a11y；
**全量 115 条在 push main 后的 `e2e-full` job 跑**，2026-09-25 拆级）；开发时**用 Playwright 手动点一次页面做验证**不属此列，不受限。

## 四端一致性（新增能力时必须同步）

同一个能力在**命令行 / AI 宿主（MCP）/ 编辑器插件 / 桌面界面**四个入口都能用是设计前提；
契约真值是 `tools/four_ends_matrix.json`，人读对照页 `docs/four-ends.md` 由它生成。

- **改法的三步**：实现（领域层）→ 矩阵登记 → `python tools/jobws.py lint four-ends --write`
  重新生成说明页。漏任一步，`python tools/jobws.py lint four-ends` 会指名报出来
  （矩阵写了但不存在、存在但没登记、说明页不同步、技能镜像与真源不一致，都拦）。
- **命名与配对规则**（检查器会验的那几条）：MCP 写工具名统一 `preview_<动作>_<资源>`；
  写入一律两段式（命令行 `--preview` → `apply`；AI 宿主 `preview_*` → `apply_approval`；
  界面靠弹窗确认）；插件命令必须在 `.codebuddy-plugin/plugin.json` 的 `commands` 里登记。
- **对齐以加法为主**：既有命令名与参数是契约（见 `skills/jwb-cli-contract`），
  重命名是破坏性变更——缺的补上、新的按规则起名，既有的只在矩阵里登记。
- 资产分发到各宿主：`python tools/jobws.py skills install`——批 10 起一次分发**三类资产**（技能 / 命令 / 子代理，落点见脚本头部注释；`--link` 是实验选项，Windows 需开发者模式）。**零克隆通道**（插件市场安装、`npx skills add`）见 README「快速开始」；**仓库内的项目级副本**由上面的检查器按资产类型逐项比对（用户级 `~/.agents/skills/` 与插件市场缓存不在视野内——它们不随仓库走，见 [`docs/support-and-compatibility.md`](support-and-compatibility.md)）。

## 文案与 i18n（界面文字一律走 t()）

- **界面文案一律走 `t()`**：key 加进 `web/frontend/src/i18n/locales/zh-CN.ts`（源语言，key 的单一真值）；`en.ts` 用 `satisfies Record<TranslationKey, string>` 在**编译期**钉住两边 key 集合一致——多一个、少一个、拼错一个都直接报错（不靠人盯）。
- **四类不翻**：代码注释（中文注释是本项目文档惯例）；领域数据（阶段 / 批次 / 轮次 / 方向 / 终态枚举、CSV 列名、接口中文字段名——它们与 `tools/jobws.py track` 和工作区文件是同一套字面量，翻了就与历史数据、CLI 对不上）；用户自己的内容；工作区里的真实文件名与目录名（保留原样，或拆 key 把它夹在中间）。
- **中文界面里的外来词一口径**：中文优先，原文放全角括号备注——`服务地址（Base URL）`、`API 密钥（API Key）`、`模型服务（Provider）`；协议与格式缩写（IMAP / CSV / JSON / PDF / JD / URL 等）保持原形，不硬译。**同一个词全库同一写法**，错误串、按钮、提示一起改，别一处一处改（2026-09-14 统一，见 [#77](https://github.com/chenxiang6663635/job-workbench/issues/77)）。
- **容器组件的文案由调用方传**：如 `FormField` 的 label/hint——组件自身写死一句默认中文同样算硬编码（`emptyLabel ?? t("…")` 才是对的写法）。
- **模块级常量表里不能调 `t()`**：改成存 `labelKey: TranslationKey`（`import type { TranslationKey }`）——类型标注是编译期护栏，渲染处再 `t()`。
- **后端错误不猜语言**：抛 `ApiError(status, code, detail, **params)`（`web/backend/apierror.py`），`detail` 保留中文原文（调试与 issue 都读它），界面文案由前端按 `err.<code>` 查语言包，查不到回落 detail。code 命名 `<域>.<语义>`，**同一语义必须复用同一 code**；用户可见的动态值（阶段名、目录名、id）走 `params`，不要在文案里写死。**未预期异常也有兜底**：`main.py` 的全局处理器把任何未捕获异常转成 `server.error` + 可读 detail（完整 traceback 进日志）——绝不让裸的 `Internal Server Error` 露到界面上（2026-09-15 实测踩到：后端被低版本解释器启动时，`imaplib` 的 TypeError 没有任何一层接住）。
- **自动检查**：`python tools/jobws.py lint i18n`（CI 跑，本地随手可跑；命中即拦）。它一起查四类问题，共同点是**漏了界面都会显示 key 名或冒出另一种语言的字**，而 tsc 与 lint 全都看不见：① 硬编码中文；② 复数 key 漏传 `count`；③ `t()` 里的 key 不存在；④ **硬编码英文**（反向盲区：中文界面下冒出英文——`t()` 之外的 JSX 裸文本、`title`/`aria-label`/`alt`/`placeholder` 字面量，以及 Electron 的窗口/对话框文案键）。④ 的范围由实现里的 `EN_SCOPE_RELS` 定义——`web/frontend/src/pages/**`、`web/frontend/src/components/**`、`web/electron/**`（2026-09-14 从 pages 扩到 components：改常量即可，别再改一遍遍历逻辑）；主进程语言包 `web/electron/i18n.js` 与前端语言包同理按路径豁免。范围从紧是有意的（误报会让人开始往清单里塞假条目，检查随即失效），**扩范围前先空跑 `--list` 把误报分类**。**它刻意不覆盖**的形态与**已知边界**（行注释之后的假命中不查、块注释内的属性字面量不查、跨行属性值不查、以 `;` 结尾的裸文本一律当代码跳过、只覆盖 `title`/`aria-label`/`alt`/`placeholder` 与 Electron 的 `title`/`message`/`detail`）写在同一段实现注释里；别把"检查通过"读成"没有英文残留"。
- **放行数据类命中**：登记进 `tools/i18n_hardcode_allowlist.txt`：`路径 = 片段1|片段2  # 理由`；**英文命中写在 `en:` 段**（`en:路径 = 片段  # 理由`）——两套豁免互不通用，写错段等于没写；前缀**必须小写**。同一文件可分多行登记（每行写自己的理由），解析时是**合并**。**只放行列出来的片段，不整文件放行**——整文件豁免曾让一个已翻译文件里藏的 4 处漏翻（列头、差异标签、按钮 tooltip）全绿通过。清单是"现状存档"：某句中文翻掉了、文件删了，必须同步删，否则脚本报「片段已不再出现 / 文件已无命中」（留着会给将来的同名中文预授权）。重新生成草稿：`python tools/jobws.py lint i18n --print-allowlist`，理由要人写。
- **验证**：改动前端后跑 `npx tsc -b` + `npx eslint .`；`npm run build` 交给 CI（本地 vite 会重写 `dist/` 的数百个文件）。

## 代码卫生（借鉴反屎山清单，精简为六条）

写代码时自查，PR 自审时复核：

1. **规模预算**（由 `jobws lint size` 自动量；存量登记在 `tools/size_allowlist.txt`）：
   - **逻辑型**（业务代码）：单文件 ≤300 行；单函数 ≤60 行、**超 80 必拆**为「编排函数 + ≥2 个 helper」；嵌套 ≤3 层。
   - **数据·声明型**（i18n 语言包、常量表、测试与 fixtures）：≤1500 行——这类代码行数多而复杂度低，与业务代码同阈值只会逼人把常量表拆碎。判定见 `tools/check_size.py` 的 `classify()`（按路径识别，脚本里的声明式段落不单列，仍按逻辑型计）。
   - **存量豁免、增量守门**：已超标的文件登记进 `tools/size_allowlist.txt`（`路径 = 行数  # 理由`），**登记值即水位线**——只许变小、不许继续膨胀；降到阈值以内时检查器会要求删掉该条目（自洁，防清单腐化）。**新文件不许再超。**
2. **提取时机（rule of three）**：同一逻辑第 2 次出现时考虑提取，第 3 次必须提取到公共模块；新增第 3 个 `if/elif` 分支且每分支 >10 行时提取 dispatch。
3. **禁静默吞错**：`except Exception: pass` 与空 `catch {}` 一律不许——至少记日志（`logger.warning` / `console.error`）。
4. **单一真值源**：同一枚举/映射/常量只允许在一个模块定义，其他位置引用它——发现第 2 处内联副本即收敛回注册处。
5. **所有运行时产品代码必须被至少一套结构检查覆盖**（2026-09-25 收口批原则化）：`.py / .ts / .tsx / .js / .mjs` × `tools/ packages/ web/backend/ web/frontend/ web/electron/ mcp/ scripts/`——规模闸门此前漏了 `web/electron` 与 `.js`（最接近用户机器的 967 行 `main.js` 恰好零治理），现已补齐；**新增运行时代码目录 / 后缀时必须同步 `tools/check_size.py` 的 `SCAN_DIRS` / `SOURCE_SUFFIX`**。
6. **失败路径双通道**（2026-09-25 收口批）：启动失败 / 后端崩溃 / 更新失败 / 还原失败 / 写冲突这类问题，必须**同时**有"用户可见消息 + 本地结构化日志"，缺一不可；诊断包字段固定（版本 / 平台 / 日志尾部），**永远排除**简历、邮件、API key、密码与工作区内容（`web/electron/diagnostics.js` + 测试锁死）。

> 来源：借鉴 thermal_comfort_code 的 anti-shit-mountain 清单，按本仓库规模精简（不搬其双阈值过渡制与 L1/L2/L3 分级）。

## 明确不做（过度工程）

`develop`/`release`/`hotfix` 分支、semantic-release、GitHub Projects 看板、需求投票工具、复杂 label 体系、独立 roadmap 站点、**PR 上的全量** Playwright E2E（2026-09-13 细化为「PR 不做全量、只留最小冒烟」、2026-09-25 拆级为「PR 最小集 + main push 全量」：`web/frontend/e2e/` 的 PR 门禁只钉「页面能开 / 无横向溢出 / 顶栏不折行 / 无控制台错误 / serious+critical a11y 为 0」，全量 115 条在 push main 后的 `e2e-full` job 跑。理由：这类布局崩实测已发生两次——英文标签挤爆顶栏、窗口标题被页面 title 覆盖——而 tsc、eslint、两条判定脚本全都测不到，只能靠真机跑）、代码签名。
（依据：`docs/research/report_dev_workflow.md` —— 单人维护项目的最小可行取舍。例外：最小 CI（2026-09-08 上线，pytest + 前端构建）、最小 UI 冒烟（2026-09-13 上线，布局 + a11y，见上条括注）；**分支保护（2026-09-08 起启用）**——线性历史 + 禁 force push（含 admin）。GitHub 分支保护无法按路径区分"代码 vs 文档"（required checks 会连带禁止一切直推），故分级靠"分支策略"节的规则自律执行，出错靠 revert 兜底。）
