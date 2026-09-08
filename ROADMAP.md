# Roadmap

A living document. Each item links to a tracking issue; finished items move to the
[changelog](CHANGELOG.md). Historical implementation records stay in
[`docs/specs/`](docs/specs/) — they are engineering provenance, not the plan.

## Now

- [ ] [#2](https://github.com/chenxiang6663635/job-workbench/issues/2) — Finish the shared UI primitive migration (batch B: Jobs & Resume; batch C: Progress, Library & Settings), with empty / loading / error states on every page
- [ ] Improve English onboarding — this README is the entry point; 简体中文 kept in sync at [README.zh-CN.md](README.zh-CN.md)
- [ ] Collect early external-user feedback on the v0.1.0 install / run experience

## Next

- [ ] [#3](https://github.com/chenxiang6663635/job-workbench/issues/3) — One-command demo workspace (`init_workspace.py --demo`) so a fresh clone shows a fully populated workbench in 30 seconds
- [ ] Reproducible desktop packaging (PyInstaller / Electron); ship a release asset once it is repeatable and clean
- [ ] [#4](https://github.com/chenxiang6663635/job-workbench/issues/4) — Expand privacy & anti-fabrication regression coverage as the Web surface grows

## Later

- Third-party domain profiles: document the contribution contract so new industries plug in without touching core code
- English UI (i18n): the interface is Chinese-first today; an English locale for international users lands here
- Richer maintainer automation (release-note drafting, changelog assembly) — only where it pays for itself
- Accessibility and localization beyond zh-CN / en
