# Roadmap

A living document. Current work is in **Now** (below the shipped log); finished
items move to the [changelog](CHANGELOG.md), and items link to a tracking issue
when one exists. Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Shipped — recent batches (details in the changelog)

- [x] **v0.3.0 "agent-ready workbench" batch (2026-09-14)** — the CLI is one entry point now (`jobws`, PR #95 — **breaking**: the old script names no longer run features, they print a migration hint and exit 2, full mapping table in the changelog); an MCP server (`jobws-mcp`, three read-only tools at v0.3.0, PR #94; the three two-phase write tools landed after) puts the tracker / job pool / dashboard in front of an agent host; **writes became two-phase everywhere** (preview → one-shot token → apply, for `track add` / `import` / `update` / `init`, PR #98 / #99) and the MCP side ships the same flow as three tools sharing one implementation; **outbound TLS got a third, safe option** (fall back to a bundled CA list when the system trust store cannot be loaded — verification stays on by default, PR #96); first-run guidance for an empty workspace (PR #100) and a data-location card in settings (PR #101); skill bodies now use command names and a check keeps repo paths out of them (PR #97); the CodeBuddy plugin shell and cross-host review assets landed (PR #102); the domain contract is written down with `jobws lint domains` + `jobws release check` (PR #103, closing B13/B14); all 14 screenshots were re-shot in both languages (PR #104). **Released 2026-09-14 as `v0.3.0`** (tag → workflow built the installer and attached it) — read the changelog before upgrading, the CLI rename is breaking. Post-release: the IMAP edge case from [#50](https://github.com/chenxiang6663635/job-workbench/issues/50) was verified against a real mailbox and closed — the extra probe connection stays, its removal is tied to the Python 3.12 baseline registered below.
- [x] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Shared UI primitive migration (batch B + batch C), empty / loading / error states on every page. Shipped in PR #15 / #16; the legacy palette still left in `Applications` / `Dashboard` / shell / `ErrorBoundary` is tracked separately as [#17](https://github.com/chenxiang6663635/job-workbench/issues/17) (2026-09-11: scheduled into the v0.2.0 batch)
- [x] Collect early external-user feedback on the install / run experience — **done, and it immediately found something worth acting on**: [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) (an English-speaking user installed it and could not use the interface). See the *English readiness* item below, which exists because of this report
- [x] **English readiness** — **closed 2026-09-13**: the interface itself is bilingual now (full i18n, PR #52/#54/#55/#56/#57/#58 → [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) closed), so every part below is resolved. README / CONTRIBUTING / issue templates were already English. **Same-day follow-up (v0.2.2)**: the *reverse* leak was cleaned too — English strings still hard-coded in the Chinese UI (settings card title, Electron window title and update dialogs) — and `tools/jobws.py lint i18n` grew a hard-coded-**English** check so the class stays closed; its scope and known limits are tracked as [#77](https://github.com/chenxiang6663635/job-workbench/issues/77).
    - [x] `docs/usage-guide.md` translated to English as the primary version, 简体中文 kept as `usage-guide.zh-CN.md`
    - [x] English trigger phrases in the 5 `SKILL.md` `description` fields — the model matches requests against those descriptions, and they are Chinese-only today, so the "just drive it from your AI CLI" path is *also* closed to an English user ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10: 随技能改名同批加上（PR #25），五个技能的描述均已含 `English triggers:`**
    - [x] Make the Chinese-first caveat land **before** the download step instead of inside a blockquote under *UI Preview* — documenting a limitation is not the same as it being acceptable ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10 进展：提示已前移到 Download 标题下；但按本项自己的标准（"记录一个限制 ≠ 这个限制可以接受"）；**2026-09-13 起界面双语，这条限制本身已被解除——提示随删除（比把提示挪位置更彻底），[#19](https://github.com/chenxiang6663635/job-workbench/issues/19) 关闭**
- [x] **v0.2.2 bilingual + hardening batch (2026-09-13)** — the interface ships bilingual (English + 简体中文, header switch, system language on first run, choice remembered); outbound TLS now follows one policy (`tools/tls_policy.py`: verify by default, refuse when the trust store can't be loaded, opt-in downgrade only — issue [#59](https://github.com/chenxiang6663635/job-workbench/issues/59)); the IMAP edges got their audit follow-ups (issue [#50](https://github.com/chenxiang6663635/job-workbench/issues/50)); accessibility pass **B15** (native radio groups replace tabs-as-segmented-controls, axe exemptions emptied, keyboard walkthrough, **all seven pages share one content width**); docs screenshots became two sets (English in `docs/screenshots/`, 简体中文 in `docs/screenshots/zh-CN/`). **Shipped: PR #75 / #76 / #78 / #79 / #80 / #81 / #85, released 2026-09-13** — see the changelog for the outbound-TLS behaviour change. (Tag `v0.2.2` was cut only after #85, which fixed a release-blocking packaging defect: the PyInstaller dependency graph missed the `tools/` modules, so the packaged backend crashed on startup — now guarded by a packaged-backend smoke step in the release workflow.)
- [x] **v0.2.0 closeout batch (2026-09-11)** — job pool ↔ tracker linking (directory-name match + one-click apply), job pool four sorts + status filter, dashboard "high-score not applied" + score-tier × status distribution; legacy palette migration ([#17](https://github.com/chenxiang6663635/job-workbench/issues/17)); regression expansion ([#4](https://github.com/chenxiang6663635/job-workbench/issues/4)); then a single-pass re-shoot of all 7 screenshots and release **v0.2.0** — which carries the breaking `jwb-` skill rename (migration steps go into the Release notes). **Shipped: PR #29 / #30 / #31 / #32 / #33 / #34, released 2026-09-12**

### Earlier batches (details in the changelog)

- [x] Reproducible desktop packaging (PyInstaller backend exe → Electron NSIS) — shipped as `job-workbench-setup-0.1.1-win64.exe` on the v0.1.1 release; one-command rebuild via `scripts/build_desktop.ps1`
- [x] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds — shipped in PR #20
- [x] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows — **shipped in PR #32**: portability resolution, CSV-import privacy & atomicity, and doc relative-link reachability (three previously untested surfaces)
- [x] **Release automation** — shipped in PR #23: tag (`v*`) triggers the Windows build and attaches the installer to the Release, so the v0.1.1 asset drift is now structurally impossible; the v0.2.0 release will be its first real run

## Now — single-release plan (registered 2026-09-15)

**Release practice changed on 2026-09-15**: version numbers are timestamps — the release number is
`YY.MM.DD.N` (generated on release day, `N` increments for repeat releases on the same day), the
machine-readable `package.json` version is that day's `YY.M.D`, and the tag is `v<release number>`
(see [CONTRIBUTING.md](CONTRIBUTING.md), section 版本号体系). There is a **single release node**:
every batch below lands before it, none of them ships on its own, and the whole plan goes out as
**one timestamped release**. Each batch still lands as its own PR; items below carry a
**2026-09-20 verified status note** (已实现 / 部分完成 / 未开始 / **暂缓**——暂缓的条目移至下方「候选池」并写明触发条件).

- [x] **Versioning switch** (first) — timestamp release numbers end to end: the generator and the
  derived tag check in `tools/release_assist.py` (`jobws release version`), the release-workflow
  gates, the changelog / contributing rules, and an **about card in settings** showing the running
  (machine) version and platform. **Build date was dropped**: nothing ever produced
  `JOBWS_BUILD_DATE`, so the field could only render as empty (found in review, 2026-09-15).
- [x] **Question bank** — **已实现（2026-09-20 核实）**：题库成为一等公民（独立 `questions.csv`）、错题本与「今日待复习」、CSV 导入/导出、**删除与撤回**（行指纹 + 工作区外整表快照）、**抽题与重练训练面板**均已落地（后两条超出原登记范围）。原描述：stops being a mirror of interview records: a first-class personal bank
  with import/export (CSV and workspace Markdown, preview-then-apply with a one-shot token), a
  wrong-answer book and a "due today" review; the talks table follow-ups land alongside.
- [x] **UI visual pass** — **大部已落地（2026-09-20 核实）**：数字体系、字号连续可调、主题与字体体系、八页精修均已随 v0.2.x–09 月批次落地，中英两套截图已重拍（16 张）。原描述：background depth, typography scale, eight-page polish and number
  rendering (tabular figures); the acceptance bar is "a screenshot diff you can point at", carried
  over from the earlier visual-polish plan (whose token and primitive layers already shipped).
- [x] **Agent & MCP line** — **已实现（2026-09-20 核实）**：MCP 写工具协议级确认（多轮往返 + 四类拒绝用例）、领域层独立可分发包 + CI 独立安装冒烟、工作区文件资源与提示模板均已落地（PR #156 前后）。原描述：write tools move to **protocol-level confirmation** (multi-round-trip
  + signed request state, four rejection classes tested) and the domain layer is extracted into an
  installable package with a standalone-install smoke in CI; then workspace files become MCP
  resources, prompt templates ship, and the modern protocol is kept with legacy compatibility.
- [ ] **Exams track** — **暂缓（2026-09-22 拍板）**：不实现，整条降级为候选池条目（见下方「候选池」表首行，含触发条件）。原描述：stage names become per-track configuration (defaults identical to today,
  so an existing workspace changes in no way) so 考公 flows through the same workbench instead of
  a parallel one; the question bank grows exam subject presets.
- [x] **Mail structuring** — **已实现（PR #176，2026-09-23 已合并）**：日历附件优先（`.ics` 最小解析）+ 正文正则兜底抽事实——时间、会议链接、阶段、公司与岗位；建议卡**逐条确认**才写入（不确认不落盘），会议链接进邮件台账新列（缺列按空、零迁移）；引用块与签名先剥离、截断按行边界保留含链接/日期行；可选 AI 增强 BYOK、只产建议、强制低把握；**无后台路径**（无定时器 / 轮询 / 保活）。原描述：extract candidate facts from message bodies (times, meeting links,
  stages, companies) into suggestion cards that only write after row-by-row confirmation; no
  background workers, ever.
- [x] **Skills & plugin distribution** — **已实现（PR #177，2026-09-23 已合并）**：8 个技能补标准元数据（`license` / `metadata.version` / 按需 `allowed-tools`）并把最长三份的大段内容拆进 `references/`（渐进披露）；校验器加字段白名单、`references/` 可达、正文 ≤500 行与**版本号一致性**四条规则；分发从「只有技能」扩到**技能 + 命令 + 子代理**三类（`skill_assets.py` 的资产表 + `--link` 实验选项），镜像比对按资产类型泛化并进 CI；零克隆通道（插件市场 / `npx skills add`）写进 README。原描述：the eight skills move onto the cross-host standard
  distribution channel with progressive disclosure; the plugin shell grows from skills-only to
  commands + subagents; hooks stay local, auditable and off by default. **hooks 仍保持本地、默认关闭**（决策见 [`docs/decisions/keep-hooks-local-and-off.md`](docs/decisions/keep-hooks-local-and-off.md)）。
- [x] **System reminders, complete** — **已实现（2026-09-24 补全，候选池条目移出）**：提前 N 天（3/5/7 可配）+ 两类已过期（截止日期已过仍待投 / **下次动作日期已过**——后者此前哪个桶都不进）+ **按事项**去重（今天新出现的也报）+ 点通知展开该条。移出理由：候选池写的触发条件「错过截止日真实发生过」已被用户需求满足，且最小形态提醒已在收口批落地。

**Graduation (the first timestamped release is the 1.0-equivalent)**: it ships when the workbench
is stable for daily use and the workspace format promises **backward compatibility** — new columns
and tables are read as empty when missing and written with unified headers, so no user-side
conversion is ever required. **判据已成文（2026-09-22）**：四条可核的条件、支持策略与数据兼容条款见
[`docs/support-and-compatibility.md`](docs/support-and-compatibility.md)。

## Later

- [x] Third-party domain profiles — **shipped in v0.3.0** (PR #103): [`docs/domain-contract.md`](docs/domain-contract.md) is the contribution contract and `jobws lint domains` validates a third-party profile (structure + dictionaries parse), so a new industry plugs in without touching core code
- [x] **English UI (i18n)** — **shipped 2026-09-13** (details in the [changelog](CHANGELOG.md)): bilingual 简体中文 / English with a header switch, first run follows the system language, choice remembered; the domain enum *values* stay Chinese on purpose (shared contract with the CLI and your data). Closed [#19](https://github.com/chenxiang6663635/job-workbench/issues/19)
- [x] Richer maintainer automation — **partly shipped in v0.3.0** (PR #103): `jobws release check --tag v26.09.15.1` validates the tag/version match (since 2026-09-15: the date-part rule of the timestamp scheme) and the changelog section, and prints the release notes CI will publish (the workflow assembles the Release body from the changelog). Anything beyond that still has to pay for itself
- Accessibility and localization beyond zh-CN / en
- [x] Desktop auto-update (electron-updater) — **shipped in v0.2.1** (asks twice: download, then restart; the first updater-enabled version still needed one manual install)
- [x] **Real-time application status** — **shipped in v0.3.0**: the research (2026-09-11) found that no recruiting platform exposes a candidate-facing status API, so the answer is local — *paste the email* → parse (which record, what to change, and the sentence it came from) → confirm row by row → write, with a read-only IMAP pull as the optional sync on top (verified against a real mailbox, 2026-09-14). 时间与会议链接的抽取已在 `Now` 段的 **Mail structuring** 条目交付（PR #176）；宣讲会一侧的扩展登记在下方候选池

## 候选池（暂缓，逐条写明触发条件）

**这一节是什么**：暂缓事项的集中登记处。与上面 `Later` 的区别是——这些**没有承诺**，只是「想过、决定现在不做」。每条都写明**什么条件下才值得做**，将来不必重新论证一遍；已经定了「怎么做」的决策在 [`docs/README.md`](docs/README.md) 的「决策记录」一节（ADR），这里只回答「要不要做」。

**纪律**：往这里加条目只需一行「一句话 + 触发条件」；真正要开工时，先从 `Now` 走一遍四道门（`CONTRIBUTING.md` 的「新需求四道门」），再把它从这里移出去（`Now` 段只保留一行状态指针，不重复描述）。

| 候选 | 一句话 | 触发条件 |
|---|---|---|
| 考公赛道（原批 7，2026-09-22 暂缓） | 阶段名做成赛道配置（默认值与今天一致，现有工作区零改动）、题库加考公主科预设 | 确定要考公，且日常使用已稳定（先看 [`docs/support-and-compatibility.md`](docs/support-and-compatibility.md) 的毕业条件） |
| 整站 390px 适配 | 顶栏与看板网格在窄屏本就横向溢出；e2e 基线钉的只是「不再变坏」 | 手机成为主要使用场景，或基线再次被真实回归触发 |
| 宿主内渲染工作台界面 | 在 AI 宿主里开面板，而不是切到浏览器或桌面壳 | 宿主开放稳定的渲染 API，且界面成为主要使用方式 |
| 长任务扩展（面试周 / 备考周） | 一次性把一段时间的任务排开、按周复盘 | 出现连续两周以上的高强度面试或备考 |
| 浏览器表单预填 | 只预填、不提交（自动投递永不考虑，见 ADR） | 平台页面结构稳定，且用户明确要求 |
| ICS 重复会议（RRULE） | 现在只取首个实例并在卡片注明；需要时评估 `icalendar`（BSD-2） | 真实收到重复会议邀请，且因此误判过一次时间 |
| 用户级 / 插件缓存副本的一致性 | 检查器只看仓库内的项目级副本（范围说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 的「资产分发到各宿主」），用户级 `~/.agents/skills/` 与插件缓存在视野之外 | 出现「装到用户级却长期用旧版」的真实事件 |
| 依赖主版本升级（Electron 等） | 调研已做（[`docs/research/report_electron_33_to_44.md`](docs/research/report_electron_33_to_44.md)）；升级要人工批次、单独冒烟 | 安全修复需要，或宿主 / 打包链要求 |
| 文档英文润色（超出 i18n 范围） | README 与文档的英文由人过一遍（术语一致但语感生硬） | 有英文母语使用者开始用时 |
