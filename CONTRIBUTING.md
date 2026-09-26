# Contributing

Thanks for looking. This repository is a **local-first job-hunt workbench** maintained by a
single person, and it is built to be **used** before it is built to be contributed to — so
the fastest way to help is to use it and report what breaks.

Most useful contributions: bug fixes, documentation, **new domain profiles**
(see [docs/domain-contract.md](docs/domain-contract.md)), privacy safeguards, tests, and
interoperability improvements.

**This file is the short index.** The full handbook is written in Chinese (authoritative);
the English companion covers what a contributor needs to work here, and keeps the
maintainer-only sections as summaries:

- 🇨🇳 [docs/contributing.zh-CN.md](docs/contributing.zh-CN.md) — 完整中文版（权威）
- 🇬🇧 [docs/contributing.en-US.md](docs/contributing.en-US.md) — English companion (contributor sections in full; maintainer sections summarised)

## Before anything else: privacy rules

This repository holds **no real personal data** — but the local workspace does, and the
guardrails exist because it is easy to leak it by accident:

- **Never commit anything under `personal/`** (paths, real company names, résumé fragments,
  application records, screenshots). It is gitignored; do not force it in.
- **Never commit real identity information** — names, phone numbers, emails, schools, ID
  numbers, photos. Use the existing placeholders (`示例公司A`, `sample@example.com`, `13800000000`).
- **Found a leak?** Open a public issue that states **only the location**, never the content
  itself. **Found a vulnerability?** Use the private channel in [SECURITY.md](SECURITY.md) —
  no reproduction details in public issues.

Details and the two-channel rule: [handbook](docs/contributing.en-US.md#privacy-rules-in-force-since-open-sourcing--read-before-contributing)
· [中文（权威）](docs/contributing.zh-CN.md). What the app itself sends where (a different
question from what you commit) is in [docs/data-flow-matrix.md](docs/data-flow-matrix.md).

## Set up

```bash
# 1. A Python 3.12 venv (the only supported and verified baseline)
python -m venv .venv && .venv/Scripts/activate      # Windows;  .venv/bin/activate elsewhere

# 2. Backend + dev dependencies
pip install -r web/backend/requirements-dev.txt

# 3. The domain package (install it, do not merely import it from source)
pip install packages/jobws-core

# 4. Local commit guardrails (privacy + size + fast tests)
git config core.hooksPath .githooks

# 5. Frontend
cd web/frontend && npm install
```

`web/start.ps1` starts the backend (8765) and frontend (5173) together and opens the browser;
`.\start.ps1 -CheckOnly` only prints which interpreter it would use.

## Checks to run before you push

```bash
python -m pytest tests/ -q                                  # full backend suite (~40s)
python tools/jobws.py lint {i18n,ui-tokens,themes,four-ends,size}   # one check name per invocation; expand the braces
cd web/frontend && npm run lint && npm run build            # npm.cmd on Windows
```

Changed pure frontend logic? Add a case under `web/frontend/tests/unit/` (`npm run test:unit`).
Changed the UI? Also run `npm run test:ui` (needs `npm run build` first).

Four CI checks must be green before a merge: backend pytest, frontend lint + build, PR title,
and UI smoke. The full 115-case E2E suite runs after the merge, on `main`.

## The four gates for a new requirement

Walk through these before writing code — they filter out most ideas early:

1. **How many times has this come up?** First time → a throwaway script or a document, not the
   codebase; second → turn it into a configuration item; third → generalise it.
2. **Does it contain personal facts?** Anything belonging to one specific person goes into the
   `personal/` configuration layer or a domain profile, never into core code.
3. **What does generalisation cost?** ≤ 1 hour → do it along the way; > 1 hour → file an issue
   instead of breaking the structure.
4. **Does it touch the data model or the honesty red lines?** It needs its own design note
   first ([AGENTS.md](AGENTS.md) is the reference for the red lines).

## Commits and pull requests

- **Conventional Commits**: `<type>(<scope>): <subject>`, types limited to
  `feat / fix / docs / chore / refactor / data / job`. Data entry goes in separate `data:` /
  `job:` commits.
- **Subjects and PR titles must be Chinese** — this is machine-enforced, not a style
  preference (the PR title becomes the trunk commit subject after a squash merge, and the
  gate is the same implementation locally and in CI). **If you do not write Chinese, open
  the PR anyway and say so in the body.** Expect two red things, both harmless: your local
  commit is rejected by the `commit-msg` hook (**commit with `--no-verify`** and note it in
  the PR body), and the PR-title check on CI goes red. The maintainer retitles before
  merging — the obligation is recorded in the handbook (§Commit conventions). Do not fight
  the bot.
- **Everything goes through a PR** — `main` has branch protection, so even a typo fix does.
  Branch first (`git switch -c fix/123-something`), squash and merge, delete the branch.
- **Every PR gets a dual-track review**: the author reads their own diff file by file and
  posts the conclusion on the PR, then a fresh-context reviewer (a subagent, or
  `python scripts/review.py` on another CLI) reviews the same diff as a stranger. Both rounds
  stay on the PR page. Nothing is merged silently.
- Keep PRs to **one independently acceptable batch**, not one commit — small commits inside,
  a single review at the end.

## Where the details live

Sections marked *(summary)* carry a summary only in the English companion — the authoritative
full text (and the decision history) is the Chinese handbook.

| Topic | Read |
|---|---|
| Privacy rules, the four gates, review protocol | [en](docs/contributing.en-US.md#privacy-rules-in-force-since-open-sourcing--read-before-contributing) · [中文（权威）](docs/contributing.zh-CN.md) |
| Branching, commits, squash rules, branch cleanup | [en §Branching](docs/contributing.en-US.md#branching-strategy-tiered-prs--trunk-based) · [中文](docs/contributing.zh-CN.md) |
| Commit & CHANGELOG writing rules | [en §Commit conventions](docs/contributing.en-US.md#commit-conventions-conventional-commits) · [en §CHANGELOG style *(summary)*](docs/contributing.en-US.md#changelog-style-single-file-two-levels-since-2026-09-20) · [中文（权威）](docs/contributing.zh-CN.md) |
| Versioning (`YY.MM.N`) and the release process | [en §Versioning *(summary)*](docs/contributing.en-US.md#versioning-month-granularity-calver-yymmn-since-2026-09-24) · [en §Release process *(summary)*](docs/contributing.en-US.md#release-process-manual-archiving) · [release checklist](docs/release-checklist.md) · [中文（权威）](docs/contributing.zh-CN.md) |
| Release blocking list, freeze window | [en §Release governance *(summary)*](docs/contributing.en-US.md#release-governance-blocking-list--freeze-window--tiered-verification) · [中文（权威）](docs/contributing.zh-CN.md) |
| Code hygiene (size budget, no silent errors, …) | [en §Code hygiene](docs/contributing.en-US.md#code-hygiene-borrowed-from-an-anti-shit-mountain-checklist-trimmed-to-six-clauses) · [中文](docs/contributing.zh-CN.md) |
| Copy and i18n rules | [en §Copy & i18n](docs/contributing.en-US.md#copy--i18n-ui-strings-always-go-through-t) |
| Adding a capability (all four entrances) | [docs/four-ends.md](docs/four-ends.md) |
| **What data leaves your machine** (the privacy promise) | [docs/data-flow-matrix.md](docs/data-flow-matrix.md) |
| Graduation criteria, support, data compatibility | [docs/support-and-compatibility.md](docs/support-and-compatibility.md) |
| Data layering, the honesty red lines | [AGENTS.md](AGENTS.md) |
| Architecture, data and API contracts | [docs/README.md](docs/README.md) |

## Pace, conduct, security

- **A single-maintainer project, in bursts.** Some days land a batch of small PRs, some weeks
  land none — **no development during interview or exam weeks**. First response to an issue
  targets 48 hours, with slips disclosed in a pinned issue
  (see [docs/maintenance.md](docs/maintenance.md)).
- [Code of conduct](.github/CODE_OF_CONDUCT.md) · [Security policy](SECURITY.md) ·
  [Support & compatibility](docs/support-and-compatibility.md)
