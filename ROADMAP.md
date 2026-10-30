# Roadmap

A living document. Current work is in **Now** (below the shipped log); finished
items move to the [changelog](CHANGELOG.md), and items link to a tracking issue
when one exists. Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Shipped — recent batches (details in the changelog)

> **Date convention**: the date in a batch title is the **changelog version date** (the day the
> entry was cut), which can differ by a day or three from the moment the GitHub Release actually
> went public. Where they differ, both are written out below.

- [x] **v26.10.1 security hotfix (changelog 2026-10-23, released 2026-10-26 09:06 UTC)** — two dependency security updates, no functional change: `certifi` 2026.7.22 → 2026.10.19 (drops the affected **emSign ECC Root CA - G3**, PYSEC-2026-4320, CVSS 9.1) and `pypdf` 6.19.0 → 6.21.2 (five availability CVEs: unvalidated JPEG load, outline infinite loop, incomplete xref, multi-filter stream resource exhaustion). No data migration needed; sites chaining to the emSign root may report an incomplete chain after upgrading — expected. Both bumps land in `web/backend/requirements.txt` and `requirements.lock` together. Verification: [`docs/releases/26.10.1-verification.md`](docs/releases/26.10.1-verification.md); the post-release residual risk (auto-update never verified end-to-end in a public setting) was **accepted explicitly** in [`docs/releases/26.10.1-post-release-risk-acceptance.md`](docs/releases/26.10.1-post-release-risk-acceptance.md). **Two different things, do not merge them**: the *technical* gap closed on 2026-10-30 — the public auto-update chain (P-2 ~ P-5) passed on a real machine against the published release ([`docs/release-checklist.md`](docs/release-checklist.md) §〇) — while that acceptance document is still **unsigned** (§五 「☐ 待签」) and is carried as an open release blocker there; the archived record keeps P-2 ~ P-5 as `NOT_EXECUTED` and is not back-filled.
- [x] **v26.10.0 "data root" batch (changelog 2026-10-06, released 2026-10-06 10:54 UTC)** — the workspace no longer has to live inside the install: `jobws data-root set` persists the choice (atomic write, absolute paths only, `.jobws-root.json` identity file), migrating became a **resumable transaction** (copy → byte-for-byte verify → switch, delete-never, `--apply` / `--resume` / `--rollback`), a fresh install now defaults to `<user data>/job-workbench/data`, and the settings page can walk you through moving it. `jobws doctor` + a new `jobws.info` MCP tool report the real data root and one of four health states (`ok` / `ambiguous` / `uninitialized` / `unavailable`, failing closed as `sys.dataRootUnavailable`). All 15 MCP tools carry standard annotations (`readOnlyHint`; `apply_approval` is the only non-read-only one; `openWorldHint=false`). Also: `integrations/dsh/` ships the MCP hookup (`profile.patch.yml`), an optional `jobws` preset and the nine `jwb-*` skills as one bundle; credentials moved to Windows Credential Manager ([#203](https://github.com/chenxiang6663635/job-workbench/issues/203)); due-date reminder bar; the usage guide moved behind a Gitee mirror; external-change refresh fix; note cross-linking; the font-size slider now applies everywhere; an independent top bar (VS Code titleBar style, 10 themes, two contrast checks); direction options generated from the workspace's `config/directions/`. Verification: [`docs/releases/26.10.0-verification.md`](docs/releases/26.10.0-verification.md).
- [x] **v26.9.0 batch (changelog 2026-09-25, released 2026-09-26 06:28 UTC)** — hard eligibility became **four states** (pass / fail / *profile missing* / *needs confirmation* — a `[待填]` fact no longer kills a job, it is reported as "fill the profile first"), city requirements split into hard (terminates) and preference (only −3/−5 on culture & stability, capped at 5), direction anchors grew 2 → 6, and eligibility finally has tests. `jwb-domain-setup` arrived: an AI-guided, human-confirmed generator for domain plugins, gated by `jobws lint domains` before anything is written. Plus the "open original email" deep link now keys off *your* provider (only Gmail gets `rfc822msgid`; the others get a reason and a way forward), due-date reminders (report overdue first, 3/5/7 days ahead, deduped once per item per day, clicking lands on the tracker row), mail deadlines rendered as countdowns, email settings with provider presets (163/126/yeah.net declare IMAP ID; Outlook personal accounts are marked unsupported *with the reason*), a six-item pre-release closeout (one graded-confirmation primitive, one-click snapshot restore with a drill, a diagnostics bundle, window-position memory, a searchable settings page including `@modified`, due-date system notifications), two full-repo audits fixed the same day (11 findings, from lock-free read-modify-write on the secondary table silently rolling back, through `127.0.0.1:8765.evil.com` passing an Electron navigation prefix check, to unbounded whole-message email reads), governance written down (candidate pool, ADRs, support & compatibility page), and one `--link` distribution path for skills / commands / subagents. Verification: [`docs/releases/26.9.0-verification.md`](docs/releases/26.9.0-verification.md).
- [x] **v0.3.2 maintenance batch (changelog 2026-09-14, released 2026-09-15 07:46 UTC)** — three maintenance streams shipped together instead of as three versions: the desktop shell went Electron 33 → 44, the frontend build chain went Vite 5 → Vite 6, and the Python baseline went 3.8 → 3.12 — clearing **46 of 48** Dependabot alerts (the remaining two are dismissed as "known, with a reason": `extract-zip`, a build-time-only dependency with no upstream fix). **User-visible**: the installer and Start-menu product name became `Job Workbench` (was 「求职工作台」; the window title still follows the interface language), the installer grew 92.0 MB → 120.3 MB purely from upstream Chromium across 11 major versions, and running from source now needs Python 3.12+. Data, logs and zoom preferences stayed put — no migration.
- [x] **v0.3.0 "agent-ready workbench" batch (changelog 2026-09-14, released 2026-09-15 04:05 UTC)** — the CLI is one entry point now (`jobws`, PR #95 — **breaking**: the old script names no longer run features, they print a migration hint and exit 2, full mapping table in the changelog); an MCP server (`jobws-mcp`, three read-only tools at v0.3.0, PR #94; the three two-phase write tools landed after) puts the tracker / job pool / dashboard in front of an agent host; **writes became two-phase everywhere** (preview → one-shot token → apply, for `track add` / `import` / `update` / `init`, PR #98 / #99) and the MCP side ships the same flow as three tools sharing one implementation; **outbound TLS got a third, safe option** (fall back to a bundled CA list when the system trust store cannot be loaded — verification stays on by default, PR #96); first-run guidance for an empty workspace (PR #100) and a data-location card in settings (PR #101); skill bodies now use command names and a check keeps repo paths out of them (PR #97); the CodeBuddy plugin shell and cross-host review assets landed (PR #102); the domain contract is written down with `jobws lint domains` + `jobws release check` (PR #103, closing B13/B14); all 14 screenshots were re-shot in both languages (PR #104). **Released as `v0.3.0` on 2026-09-15** (changelog entry dated 2026-09-14; tag → workflow built the installer and attached it) — read the changelog before upgrading, the CLI rename is breaking. Post-release: the IMAP edge case from [#50](https://github.com/chenxiang6663635/job-workbench/issues/50) was verified against a real mailbox and closed — the extra probe connection stays, its removal is tied to the Python 3.12 baseline registered below.
- [x] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Shared UI primitive migration (batch B + batch C), empty / loading / error states on every page. Shipped in PR #15 / #16; the legacy palette still left in `Applications` / `Dashboard` / shell / `ErrorBoundary` is tracked separately as [#17](https://github.com/chenxiang6663635/job-workbench/issues/17) (2026-09-11: scheduled into the v0.2.0 batch)
- [x] Collect early external-user feedback on the install / run experience — **done, and it immediately found something worth acting on**: [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) (an English-speaking user installed it and could not use the interface). See the *English readiness* item below, which exists because of this report
- [x] **English readiness** — **closed 2026-09-13**: the interface itself is bilingual now (full i18n, PR #52/#54/#55/#56/#57/#58 → [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) closed), so every part below is resolved. README / CONTRIBUTING / issue templates were already English. **Same-day follow-up (v0.2.2)**: the *reverse* leak was cleaned too — English strings still hard-coded in the Chinese UI (settings card title, Electron window title and update dialogs) — and `tools/jobws.py lint i18n` grew a hard-coded-**English** check so the class stays closed; its scope and known limits are tracked as [#77](https://github.com/chenxiang6663635/job-workbench/issues/77).
    - [x] `docs/usage-guide.md` translated to English as the primary version, 简体中文 kept as `usage-guide.zh-CN.md`
    - [x] English trigger phrases in the 5 `SKILL.md` `description` fields — the model matches requests against those descriptions, and they are Chinese-only today, so the "just drive it from your AI CLI" path is *also* closed to an English user ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10: 随技能改名同批加上（PR #25），五个技能的描述均已含 `English triggers:`**
    - [x] Make the Chinese-first caveat land **before** the download step instead of inside a blockquote under *UI Preview* — documenting a limitation is not the same as it being acceptable ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10 进展：提示已前移到 Download 标题下；但按本项自己的标准（"记录一个限制 ≠ 这个限制可以接受"）；**2026-09-13 起界面双语，这条限制本身已被解除——提示随删除（比把提示挪位置更彻底），[#19](https://github.com/chenxiang6663635/job-workbench/issues/19) 关闭**
- [x] **v0.2.2 bilingual + hardening batch (changelog 2026-09-13, released 2026-09-14 03:59 UTC)** — the interface ships bilingual (English + 简体中文, header switch, system language on first run, choice remembered); outbound TLS now follows one policy (`tools/tls_policy.py`: verify by default, refuse when the trust store can't be loaded, opt-in downgrade only — issue [#59](https://github.com/chenxiang6663635/job-workbench/issues/59)); the IMAP edges got their audit follow-ups (issue [#50](https://github.com/chenxiang6663635/job-workbench/issues/50)); accessibility pass **B15** (native radio groups replace tabs-as-segmented-controls, axe exemptions emptied, keyboard walkthrough, **all seven pages share one content width**); docs screenshots became two sets (English in `docs/screenshots/`, 简体中文 in `docs/screenshots/zh-CN/`). **Shipped: PR #75 / #76 / #78 / #79 / #80 / #81 / #85** (changelog entry dated 2026-09-13; the tag went out on 2026-09-14) — see the changelog for the outbound-TLS behaviour change. (Tag `v0.2.2` was cut only after #85, which fixed a release-blocking packaging defect: the PyInstaller dependency graph missed the `tools/` modules, so the packaged backend crashed on startup — now guarded by a packaged-backend smoke step in the release workflow.)
- [x] **v0.2.1 desktop auto-update (changelog 2026-09-12, released 2026-09-12 05:19 UTC)** — the installer checks for a new version by itself, but **asks before downloading and asks again before restarting** (closing the window also ends the backend process, so the moment is yours to pick). This release still has to be installed by hand once — the updater has to exist inside the already-installed version before later versions can update themselves; the order cannot be reversed. Release assets gained `latest.yml` and block maps (the only thing the client reads to decide whether an update exists and which file to fetch; a missing `latest.yml` is invisible from the exe alone, and a missing block map silently degrades to a full download). Artifact renaming moved into `build.artifactName` so the name in `latest.yml` matches the asset byte for byte. The installer is **not code-signed** — SmartScreen may warn; recorded as-is rather than waved away.
- [x] **v0.2.0 closeout batch (changelog 2026-09-11, released 2026-09-12 03:52 UTC)** — job pool ↔ tracker linking (directory-name match + one-click apply), job pool four sorts + status filter, dashboard "high-score not applied" + score-tier × status distribution; legacy palette migration ([#17](https://github.com/chenxiang6663635/job-workbench/issues/17)); regression expansion ([#4](https://github.com/chenxiang6663635/job-workbench/issues/4)); then a single-pass re-shoot of all 7 screenshots and release **v0.2.0** — which carries the breaking `jwb-` skill rename (migration steps go into the Release notes). **Shipped: PR #29 / #30 / #31 / #32 / #33 / #34, released 2026-09-12**

### Earlier batches (details in the changelog)

- [x] Reproducible desktop packaging (PyInstaller backend exe → Electron NSIS) — shipped as `job-workbench-setup-0.1.1-win64.exe` on the v0.1.1 release; one-command rebuild via `scripts/build_desktop.ps1`
- [x] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds — shipped in PR #20
- [x] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows — **shipped in PR #32**: portability resolution, CSV-import privacy & atomicity, and doc relative-link reachability (three previously untested surfaces)
- [x] **Release automation** — shipped in PR #23: tag (`v*`) triggers the Windows build and attaches the installer to the Release, so the v0.1.1 asset drift is now structurally impossible; the v0.2.0 release will be its first real run

## Now — 积累期收口：桶三待触发，两个发布物待落章（2026-10-09 登记，2026-10-30 更新）

**当前状态（2026-10-30）**

- **积累期三桶已收口两桶，当前没有在做的功能**：桶一（取号前小修批，2026-10-09）与
  桶二（积累期主线，2026-10-12）都已完成，逐项见 [CHANGELOG](CHANGELOG.md) 的 `[Unreleased]`。
  余下只有桶三——触发条件驱动，不主动开工。
- **两个发布物已就绪、待落章**（都是「技术侧完成、缺落章动作」，不是「还在做」）：
  - **`26.10.2` 安全 hotfix**（分支 `release/26.10.2`）：Electron `44.4.5` → `44.10.0`，
    只动依赖与版本号，不带 main 上的任何修复。属「四类阻断」里的**安全**一类，
    不占 `26.11.0` 的功能预算。tag 前的核对清单见
    [`docs/handover/2026-10-28-p0-closure.md`](docs/handover/2026-10-28-p0-closure.md)。
  - **DSH 双包随 `26.11.0` 一并首发**：`integrations/dsh/` 的主包与平台子包
    （`dsh-job-workbench` / `dsh-job-workbench-win32-x64`）技术侧**已完整**——
    自包含 runtime + `prebuilds.json` 哈希清单 + `prepack` 校验 + 17 工具冒烟 +
    227/227 逐字节可复现。**缺的不是技术，是落章六处**。执行单见
    [`docs/handover/2026-10-28-dsh-first-release-runbook.md`](docs/handover/2026-10-28-dsh-first-release-runbook.md)：
    落章 → `-FromLock` 重建 → 双包预检 + 冒烟 → 子包先主包后发布 →
    公共 npm 全新安装核验 → marketplace 收录（必须在主包发布之后）。
- [x] **16 张截图已重拍（2026-10-30，Nord 主题）**——`npm run capture -- --theme nord`，
  中英各 8 张。截图脚本跑在 `dist` 上，并且会拒绝拍旧构建（`dist 比 src 旧` 时直接 exit 2），
  所以这批图反映的是当天的界面。README 首屏四张与两个图库文档
  （[`docs/screenshots.md`](docs/screenshots.md) / [`docs/screenshots.zh-CN.md`](docs/screenshots.zh-CN.md)）
  都已指向新图。`ROADMAP` 这一条不再有待办。

**怎么走到这里的**：上一段「DSH 接入件第二阶段：自包含发行物」已全部完结（P2-1…P2-5 +
文档收口，PR #281–#286；逐项见 [CHANGELOG](CHANGELOG.md)），`v26.10.0` 已于 2026-10-06 发布。
用户拍板**暂不发布**：发布节点维持 `26.11.0`（十一月换月）。候选清单来自 2026-10-08 积累期
审计（四路并行侦察 + 外部对照），报告归档
[`docs/research/2026-10-08-accumulate-backlog-audit.md`](docs/research/2026-10-08-accumulate-backlog-audit.md)。

**三桶推进**（桶一 → 桶二 → 桶三；桶三只登记、不主动开工）：

- [x] **桶一：取号前小修批**（一个 PR，2026-10-09）— 正确性六项（评分档位小数缝隙、
  插件解析字母序兜底、CLI 默认工作区零校验、令牌簿记三连、渲染临时文件前缀、
  `history.csv` 双保险）+ `jd_score` 纯函数测试群 + 登记漂移回填 + 站点口径收口 +
  治理四项（远端已合并分支清理、#204/#259 核对、审计报告归档）。
- [x] **桶二：积累期主线**（2026-10-12 收口；各站逐项见 [CHANGELOG](CHANGELOG.md) 的
  `[Unreleased]`）— 测试盲区（JD↔简历差距链路 / `mail_dates` / 硬门槛判定复核）、
  读放大优化（`--durations` 观测后接 xdist：45s → 19s）、重复实现收编（越界判据 /
  CSV 读取 / ISO 日期，收编后 `cross_end_audit` 复核）、贴线文件拆（`tools_readonly` /
  `prep` 等）、前端体验（路由懒加载 / 长表虚拟化 / 数据根设置页入口 / 笔记图片端点）、
  双语（术语表 / 文档索引 / 用户可见模板的英文对照版）与 a11y（显示层收齐 / skip-link /
  390 三页基线）、CodeQL 静态扫描接入（#207 follow-up）、**DSH `jobws://` 只读资源核验**
  （结论：DSH 不桥接 MCP 资源 → 新增 `read_job_text` 工具入口、三个技能改走工具）。
- [ ] **桶三：触发条件驱动**（不主动开工）— 390 整站、托盘、ICS RRULE、Outlook
  OAuth2、Electron 主版本升级、代码签名、winget、国内直链、macOS、marketplace 收录
  （**必须在 npm 首发之后**）。凡涉发布物形态与元数据者：取号前落定或顺延。

**发布节点**：`26.11.0`（十一月发车，单一发布节点）。两次 hotfix 只留给四类阻断
（安全 / 数据损坏 / 安装·启动阻断 / 更新链失效）：`26.10.1` 已按这条线发出
（CHANGELOG 段头 2026-10-23，GitHub Release 公开于 2026-10-26 09:06 UTC），
`26.10.2` 同样按这条线待落章。

**一处仍需人处理的手续**（不影响本条判断，但不能当它已闭合）：`26.10.1` 的
[风险接受文件](docs/releases/26.10.1-post-release-risk-acceptance.md) §五 仍是「☐ 待签」。
2026-10-30 真机跑通的是**技术验证**（P-2 ~ P-5），不等于那份文书签完——
按「不得倒签」，要么补真实签字凭据，要么维持「待签」。见
[`docs/release-checklist.md`](docs/release-checklist.md) §〇 的同名未闭合项。


**Graduation (the first timestamped release is the 1.0-equivalent)**: it ships when the workbench
is stable for daily use and the workspace format promises **backward compatibility** — new columns
and tables are read as empty when missing and written with unified headers, so no user-side
conversion is ever required. **判据已成文（2026-09-22）**：四条可核的条件、支持策略与数据兼容条款见
[`docs/support-and-compatibility.md`](docs/support-and-compatibility.md)。

**毕业判定（2026-10-09）**：四条判据全部满足——① 连续 14 天自用无阻断（dev 栈，9-26 起）；
② 主流程冒烟全绿（八页 + CLI + CI 全 job，`v26.10.0` 上）；③ 无未决 P0/MAJOR（开放
issue 仅 minor/跟踪类）；④ 兼容条款经 `v26.10.0` 升级真机复装验证（旧工作区直接打开）。
判定证据见 [`docs/releases/26.10.0-verification.md`](docs/releases/26.10.0-verification.md)。

## Later

- [x] Third-party domain profiles — **shipped in v0.3.0** (PR #103): [`docs/domain-contract.md`](docs/domain-contract.md) is the contribution contract and `jobws lint domains` validates a third-party profile (structure + dictionaries parse), so a new industry plugs in without touching core code
- [x] **English UI (i18n)** — **shipped 2026-09-13** (details in the [changelog](CHANGELOG.md)): bilingual 简体中文 / English with a header switch, first run follows the system language, choice remembered; the domain enum *values* stay Chinese on purpose (shared contract with the CLI and your data). Closed [#19](https://github.com/chenxiang6663635/job-workbench/issues/19)
- [x] Richer maintainer automation — **partly shipped in v0.3.0** (PR #103): `jobws release check --tag v26.9.0` validates the tag/version match (since 2026-09-24: exact equality under the month-granularity CalVer scheme) and the changelog section, and prints the release notes CI will publish (the workflow assembles the Release body from the changelog). Anything beyond that still has to pay for itself
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
| 宿主内渲染工作台界面（DSH 原生面板，方案 D 已设计） | 在 AI 宿主里开**只读**面板，而不是切到浏览器或桌面壳。设计见 [`docs/specs/2026-10-19-dsh-native-workbench.md`](docs/specs/2026-10-19-dsh-native-workbench.md)：左对话、右只读（实测约 320px），八模块压成「常用 + 更多」。**阻断在数据通道**：`rpc.handle()` 已证实不可用；`connection.fetch.register()` 静态核查通过、**运行时往返未验证**。渲染扩展点本身有先例（`dsh-better-sidebar`），所以问题不是「宿主不支持 UI」，而是「右栏取不到数据」 | ① 客户端 ↔ Node 最小往返在**真机**通过（含 `fetch.register` 运行时验证）；② 只读边界进四端矩阵，「写入回 MCP 两段式」写进 [`docs/four-ends.md`](docs/four-ends.md) 的「各端不提供的能力」；③ 断线 / 权限失败有可见提示；④ 宿主退出能回收子进程（spec §三 第 7 条：SIGKILL 后 MCP exe 残留）。四条全过才从候选池移进 `Now` |
| 长任务扩展（面试周 / 备考周） | 一次性把一段时间的任务排开、按周复盘 | 出现连续两周以上的高强度面试或备考 |
| 浏览器表单预填 | 只预填、不提交（自动投递永不考虑，见 ADR） | 平台页面结构稳定，且用户明确要求 |
| ICS 重复会议（RRULE） | 现在只取首个实例并在卡片注明；需要时评估 `icalendar`（BSD-2） | 真实收到重复会议邀请，且因此误判过一次时间 |
| 用户级 / 插件缓存副本的一致性 | 检查器只看仓库内的项目级副本（范围说明见 [`CONTRIBUTING.md`](CONTRIBUTING.md) 的「资产分发到各宿主」），用户级 `~/.agents/skills/` 与插件缓存在视野之外 | 出现「装到用户级却长期用旧版」的真实事件 |
| 依赖主版本升级（Electron 等） | 调研已做（[`docs/research/report_electron_33_to_44.md`](docs/research/report_electron_33_to_44.md)）；升级要人工批次、单独冒烟 | 安全修复需要，或宿主 / 打包链要求 |
| 文档英文润色（超出 i18n 范围） | README 与文档的英文由人过一遍（术语一致但语感生硬） | 有英文母语使用者开始用时 |
| 托盘常驻 + 开机自启 | 关窗后退到托盘、继续发到点提醒（带总开关）。现在**关窗即停**——刻意的轻量取舍（工具类惯例：VS Code / Obsidian 也是关窗即退；驻留托盘属"持续通知职责"类应用） | 提醒成为日常依赖（真实发生过"关着窗口错过截止"），或用户明确要求后台常驻 |
| 区域可拖拽组合布局（桌面端） | 面板 / 分栏可拖放重组（候选库：dockview / flexlayout-react）；需要新的布局容器模型、持久化与每页迁移，8 页响应式基线要重写 | 多屏 / 宽屏成为主要使用方式，或面板重排成为日常诉求（先看 UI 线 A / B 落地后的真实使用） |
| offer / 薪酬差比较（2026-10-08 外部对照） | 多 offer 条款与薪酬差本地分析——敏感数据恰是「本地优先」的优势场景 | 同时持有两个以上真实 offer，且比较需要表格化 |
| 按 JD 定向模拟面试出题 | 题库→按 JD 生成定向题组 + 复盘链路（已有 `bank drill` 与复盘卡，增量小；中英信息源近一年共同热点） | 真实面试邀约给出 JD 后想练定向题 |
| 简历「AI 味」自检 | 面向反 AI 筛查的生成度 / 个性化检查，输出改写建议而非代写（与本仓诚实红线天然契合） | 出现因「AI 味」被筛的真实反馈 |
| 浏览器扩展一键收职位 | 招聘页一键书签进看板（Teal 式形态） | 技术债「本地 API token」先行，且手动录入成为日常负担 |
| 决策分歧留痕（系统建议 vs 用户选择） | 把「系统当时的建议」与「用户最终决定」作为**两条独立记录**持久化（原建议档位与分数、覆盖行为、可选理由、是否已实际提交），使未来能回查某次决策及其当时依据。**现状**：`tracker.csv` 有「评分 / 状态原因 / 备注」，`history.csv` 记录字段变更——这是**字段留痕**，不是决策分歧审计；`jwb-apply` 在总分低于 45 时会先询问用户是否仍要投递，但该确认**不落盘为可回查的决策记录** | 要在任何对外材料里主张「覆盖系统建议会被记录」之前（必须先有数据契约 + 写入路径 + 回读证据三件）；或真实出现「用户想保留某次低分投递的决策依据」的诉求 |
| 投递决策语义跨端统一 | `jd_score.verdict()` 返回的是**档位与动作文本**，不是权限检查器；而 `jwb-jd` 硬门槛失败即终止、`jwb-apply` 低于 45 先询问、Web 与 MCP 各有规则——这是**跨工作流语义不一致**，不是"全局低分禁令" | 出现「同一岗位在不同入口得到相反投递建议」的真实反馈，或要为决策语义做对外说明 |
| 求职行动中心 | 把已有提醒/健康度/静默项串成「下一步该做什么」，每条给**可执行动作**（深链到对应表单或页面）而不只是提醒文字；完成后再回读标记。**现状**：看板已有近期待办、到期提醒、长期静默项目与健康度诊断，但停在"提示"层，用户仍需自己判断去哪一页做什么。**第一阶段只读现有数据**，不加新字段，先验证是否真的减少跨页次数 | 真实反馈「看到提醒到完成动作仍要跨多页」，或首次上手观察（3–5 位真实测试者）中出现同类卡点 |
| 单岗位全过程视图 | 一个岗位集中看到 JD、评分、简历版本、投递记录、邮件、面试与 Offer 关系（现在分散在四个页面）。**只做聚合适配 + 深链跳转**，不新建数据模型、不做第二套业务定义 | 与「求职行动中心」同期验证；或出现「某个岗位的完整记录要找很久」的真实反馈 |
| 校招流程模板（中国校园招聘） | 借领域插件架构提供**可选**阶段模板（体检、网签、学院审核、签约材料、解约），允许自定义阶段/材料附件/截止时间；清单里区分「用户录入的事实 / 从文件提取未经核实 / 系统建议 / 需用户自行确认的校方与单位规定」。**明确不宣称**能代办学企签约、不提供法律结论 | 有校招用户实际使用并反馈现有阶段不够用（当前阶段模型是通用投递/面试/Offer） |
| 数据根受控反向迁移协议（#304 后续） | 把数据根从 B 搬回 A 时走与正向同一套清单 / 预检 / 逐字节校验 / 切换，并在开始前显式确认「B 上可能有 A 没有的新数据」。**当前版本做不到**：`root_id` 随数据一起搬走，把旧位置当目标会被误判成「已经是当前数据」（数据一动不动），或被执行目标非空预检拦下；`_already_current` 的 `root_id` 子句过度宽松，重新设计时应改为只在「目标即当前活动根」时跳过。口径已如实更正（#305），提示与文档都不再声称这条路走得通 | 真有用户需要搬回旧位置，且愿意接受「先备份目标根 + 逐字节校验」的完整流程；或出现第二例同类诉求 |
