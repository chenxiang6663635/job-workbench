# Roadmap

A living document. Each item links to a tracking issue; finished items move to the
[changelog](CHANGELOG.md). Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Now

- [x] **v0.3.0 "agent-ready workbench" batch (2026-09-14)** — the CLI is one entry point now (`jobws`, PR #95 — **breaking**: the old script names no longer run features, they print a migration hint and exit 2, full mapping table in the changelog); a **read-only MCP server** (`jobws-mcp`, three tools, PR #94) puts the tracker / job pool / dashboard in front of an agent host; **writes became two-phase everywhere** (preview → one-shot token → apply, for `track add` / `import` / `update` / `init`, PR #98 / #99) and the MCP side ships the same flow as three tools sharing one implementation; **outbound TLS got a third, safe option** (fall back to a bundled CA list when the system trust store cannot be loaded — verification stays on by default, PR #96); first-run guidance for an empty workspace (PR #100) and a data-location card in settings (PR #101); skill bodies now use command names and a check keeps repo paths out of them (PR #97); the CodeBuddy plugin shell and cross-host review assets landed (PR #102); the domain contract is written down with `jobws lint domains` + `jobws release check` (PR #103, closing B13/B14); all 14 screenshots were re-shot in both languages (PR #104). **Released 2026-09-14 as `v0.3.0`** (tag → workflow built the installer and attached it) — read the changelog before upgrading, the CLI rename is breaking. Post-release: the IMAP edge case from [#50](https://github.com/chenxiang6663635/job-workbench/issues/50) was verified against a real mailbox and closed — the extra probe connection stays, its removal is tied to the Python 3.12 baseline registered below.
- [x] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Shared UI primitive migration (batch B + batch C), empty / loading / error states on every page. Shipped in PR #15 / #16; the legacy palette still left in `Applications` / `Dashboard` / shell / `ErrorBoundary` is tracked separately as [#17](https://github.com/chenxiang6663635/job-workbench/issues/17) (2026-09-11: scheduled into the v0.2.0 batch)
- [x] Collect early external-user feedback on the install / run experience — **done, and it immediately found something worth acting on**: [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) (an English-speaking user installed it and could not use the interface). See the *English readiness* item below, which exists because of this report
- [x] **English readiness** — **closed 2026-09-13**: the interface itself is bilingual now (full i18n, PR #52/#54/#55/#56/#57/#58 → [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) closed), so every part below is resolved. README / CONTRIBUTING / issue templates were already English. **Same-day follow-up (v0.2.2)**: the *reverse* leak was cleaned too — English strings still hard-coded in the Chinese UI (settings card title, Electron window title and update dialogs) — and `tools/jobws.py lint i18n` grew a hard-coded-**English** check so the class stays closed; its scope and known limits are tracked as [#77](https://github.com/chenxiang6663635/job-workbench/issues/77).
    - [x] `docs/usage-guide.md` translated to English as the primary version, 简体中文 kept as `usage-guide.zh-CN.md`
    - [x] English trigger phrases in the 5 `SKILL.md` `description` fields — the model matches requests against those descriptions, and they are Chinese-only today, so the "just drive it from your AI CLI" path is *also* closed to an English user ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10: 随技能改名同批加上（PR #25），五个技能的描述均已含 `English triggers:`**
    - [x] Make the Chinese-first caveat land **before** the download step instead of inside a blockquote under *UI Preview* — documenting a limitation is not the same as it being acceptable ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19)). **2026-09-10 进展：提示已前移到 Download 标题下；但按本项自己的标准（"记录一个限制 ≠ 这个限制可以接受"）；**2026-09-13 起界面双语，这条限制本身已被解除——提示随删除（比把提示挪位置更彻底），[#19](https://github.com/chenxiang6663635/job-workbench/issues/19) 关闭**
- [x] **v0.2.2 bilingual + hardening batch (2026-09-13)** — the interface ships bilingual (English + 简体中文, header switch, system language on first run, choice remembered); outbound TLS now follows one policy (`tools/tls_policy.py`: verify by default, refuse when the trust store can't be loaded, opt-in downgrade only — issue [#59](https://github.com/chenxiang6663635/job-workbench/issues/59)); the IMAP edges got their audit follow-ups (issue [#50](https://github.com/chenxiang6663635/job-workbench/issues/50)); accessibility pass **B15** (native radio groups replace tabs-as-segmented-controls, axe exemptions emptied, keyboard walkthrough, **all seven pages share one content width**); docs screenshots became two sets (English in `docs/screenshots/`, 简体中文 in `docs/screenshots/zh-CN/`). **Shipped: PR #75 / #76 / #78 / #79 / #80 / #81 / #85, released 2026-09-13** — see the changelog for the outbound-TLS behaviour change. (Tag `v0.2.2` was cut only after #85, which fixed a release-blocking packaging defect: the PyInstaller dependency graph missed the `tools/` modules, so the packaged backend crashed on startup — now guarded by a packaged-backend smoke step in the release workflow.)
- [x] **v0.2.0 closeout batch (2026-09-11)** — job pool ↔ tracker linking (directory-name match + one-click apply), job pool four sorts + status filter, dashboard "high-score not applied" + score-tier × status distribution; legacy palette migration ([#17](https://github.com/chenxiang6663635/job-workbench/issues/17)); regression expansion ([#4](https://github.com/chenxiang6663635/job-workbench/issues/4)); then a single-pass re-shoot of all 7 screenshots and release **v0.2.0** — which carries the breaking `jwb-` skill rename (migration steps go into the Release notes). **Shipped: PR #29 / #30 / #31 / #32 / #33 / #34, released 2026-09-12**

## Next

- [x] Reproducible desktop packaging (PyInstaller backend exe → Electron NSIS) — shipped as `job-workbench-setup-0.1.1-win64.exe` on the v0.1.1 release; one-command rebuild via `scripts/build_desktop.ps1`
- [x] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds — shipped in PR #20
- [x] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows — **shipped in PR #32**: portability resolution, CSV-import privacy & atomicity, and doc relative-link reachability (three previously untested surfaces)
- [x] **Release automation** — shipped in PR #23: tag (`v*`) triggers the Windows build and attaches the installer to the Release, so the v0.1.1 asset drift is now structurally impossible; the v0.2.0 release will be its first real run

## Registered next (2026-09-15, single-release plan)

**Release practice changed on 2026-09-15**: version numbers are timestamps — the release number is
`YY.MM.DD.N` (generated on release day, `N` increments for repeat releases on the same day), the
machine-readable `package.json` version is that day's `YY.M.D`, and the tag is `v<release number>`
(see [CONTRIBUTING.md](CONTRIBUTING.md), section 版本号体系). There is a **single release node**:
every batch below lands before it, none of them ships on its own, and the whole plan goes out as
**one timestamped release**. Each batch still lands as its own PR.

- [ ] **Versioning switch** (first) — timestamp release numbers end to end: the generator and the
  derived tag check in `tools/release_assist.py` (`jobws release version`), the release-workflow
  gates, the changelog / contributing rules, and an **about card in settings** showing the running
  version (plus build date and platform).
- [ ] **Question bank** — stops being a mirror of interview records: a first-class personal bank
  with import/export (CSV and workspace Markdown, preview-then-apply with a one-shot token), a
  wrong-answer book and a "due today" review; the talks table follow-ups land alongside.
- [ ] **UI visual pass** — background depth, typography scale, seven-page polish and number
  rendering (tabular figures); the acceptance bar is "a screenshot diff you can point at", carried
  over from the earlier visual-polish plan (whose token and primitive layers already shipped).
- [ ] **Agent & MCP line** — write tools move to **protocol-level confirmation** (multi-round-trip
  + signed request state, four rejection classes tested) and the domain layer is extracted into an
  installable package with a standalone-install smoke in CI; then workspace files become MCP
  resources, prompt templates ship, and the modern protocol is kept with legacy compatibility.
- [ ] **Exams track** — stage names become per-track configuration (defaults identical to today,
  so an existing workspace changes in no way) so 考公 flows through the same workbench instead of
  a parallel one; the question bank grows exam subject presets.
- [ ] **Mail structuring** — extract candidate facts from message bodies (times, meeting links,
  stages, companies) into suggestion cards that only write after row-by-row confirmation; no
  background workers, ever.
- [ ] **Skills & plugin distribution** — the eight skills move onto the cross-host standard
  distribution channel with progressive disclosure; the plugin shell grows from skills-only to
  commands + subagents; hooks stay local, auditable and off by default.

**Graduation (the first timestamped release is the 1.0-equivalent)**: it ships when the workbench
is stable for daily use and the workspace format promises **backward compatibility** — new columns
and tables are read as empty when missing and written with unified headers, so no user-side
conversion is ever required.

## Later

- [x] Third-party domain profiles — **shipped in v0.3.0** (PR #103): [`docs/domain-contract.md`](docs/domain-contract.md) is the contribution contract and `jobws lint domains` validates a third-party profile (structure + dictionaries parse), so a new industry plugs in without touching core code
- [x] **English UI (i18n)** — **shipped 2026-09-13** (details in the [changelog](CHANGELOG.md)): bilingual 简体中文 / English with a header switch, first run follows the system language, choice remembered; the domain enum *values* stay Chinese on purpose (shared contract with the CLI and your data). Closed [#19](https://github.com/chenxiang6663635/job-workbench/issues/19)
- [x] Richer maintainer automation — **partly shipped in v0.3.0** (PR #103): `jobws release check --tag v26.09.15.1` validates the tag/version match (since 2026-09-15: the date-part rule of the timestamp scheme) and the changelog section, and prints the release notes CI will publish (the workflow assembles the Release body from the changelog). Anything beyond that still has to pay for itself
- Accessibility and localization beyond zh-CN / en
- [x] Desktop auto-update (electron-updater) — **shipped in v0.2.1** (asks twice: download, then restart; the first updater-enabled version still needed one manual install)
- [x] **Real-time application status** — **shipped in v0.3.0**: the research (2026-09-11) found that no recruiting platform exposes a candidate-facing status API, so the answer is local — *paste the email* → parse (which record, what to change, and the sentence it came from) → confirm row by row → write, with a read-only IMAP pull as the optional sync on top (verified against a real mailbox, 2026-09-14). Extending the extraction to times, meeting links and talks is registered below
