# Roadmap

A living document. Each item links to a tracking issue; finished items move to the
[changelog](CHANGELOG.md). Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Now

- [x] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Shared UI primitive migration (batch B + batch C), empty / loading / error states on every page. Shipped in PR #15 / #16; the legacy palette still left in `Applications` / `Dashboard` / shell / `ErrorBoundary` is tracked separately as [#17](https://github.com/chenxiang6663635/job-workbench/issues/17)
- [x] Collect early external-user feedback on the install / run experience — **done, and it immediately found something worth acting on**: [#19](https://github.com/chenxiang6663635/job-workbench/issues/19) (an English-speaking user installed it and could not use the interface). See the *English readiness* item below, which exists because of this report
- [ ] **English readiness (three parts, cheapest first)** — README / CONTRIBUTING / issue templates are already English; what's left:
    - [ ] `docs/usage-guide.md` translated to English as the primary version, 简体中文 kept as `usage-guide.zh-CN.md`
    - [ ] English trigger phrases in the 5 `SKILL.md` `description` fields — the model matches requests against those descriptions, and they are Chinese-only today, so the "just drive it from your AI CLI" path is *also* closed to an English user ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19))
    - [ ] Make the Chinese-first caveat land **before** the download step instead of inside a blockquote under *UI Preview* — documenting a limitation is not the same as it being acceptable ([#19](https://github.com/chenxiang6663635/job-workbench/issues/19))

## Next

- [x] Reproducible desktop packaging (PyInstaller backend exe → Electron NSIS) — shipped as `job-workbench-setup-0.1.1-win64.exe` on the v0.1.1 release; one-command rebuild via `scripts/build_desktop.ps1`
- [ ] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds — **implemented, in review as PR #20**
- [ ] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows
- [ ] **Release automation**: tag (`v*`) triggers a Windows build and attaches the installer to the Release. The v0.1.1 asset was built before batch B/C and no longer matches the code — that drift is structurally impossible once the asset is produced by the tag

## Later

- Third-party domain profiles: document the contribution contract so new industries plug in without touching core code
- **English UI (i18n)**: the interface is Chinese-first today and **no translation layer exists** (no i18n library, every string hardcoded), so this is a from-scratch addition rather than a patch. Scope depends on [#19](https://github.com/chenxiang6663635/job-workbench/issues/19): a *bilingual shell* (nav, buttons, empty/error states, form labels — user content stays as the user wrote it) is a far smaller job than translating everything
- Richer maintainer automation (release-note drafting, changelog assembly) — only where it pays for itself
- Accessibility and localization beyond zh-CN / en
