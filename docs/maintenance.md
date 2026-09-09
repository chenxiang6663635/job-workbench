# Maintenance

How this repository is maintained. Written down so expectations are explicit —
for contributors and for anyone evaluating the project's health.

## Release cadence

- Releases are cut when there is something meaningful to ship, typically every
  1–3 weeks. No fixed calendar.
- Versioning: semver; during 0.x, breaking changes bump the minor. The full
  discipline lives in [CONTRIBUTING.md](../CONTRIBUTING.md).
- Every release gets a changelog entry ([CHANGELOG.md](CHANGELOG.md)) and
  GitHub release notes.

## Issue triage

- **First response within 48 hours** — even if the answer is just
  "reproduced, will look into it" or "need more info".
- Labels stay minimal: `bug`, `feature`, `docs`. No priority or status
  taxonomies for a single-maintainer project.
- Issues are closed with a written conclusion (fixed in PR #X / won't fix
  because Y / duplicate of Z). Silent closure doesn't happen.

## Pull requests

- Every code PR gets a per-file review **before merge**, recorded as a PR
  comment — see the SOP in [CONTRIBUTING.md](../CONTRIBUTING.md).
- CI must be green (backend tests + frontend build) before merge; squash
  merges only, linear history.

## Maintenance rhythm

- 1–2 small PRs per week, driven by actual usage — no batch dumps, no
  performative activity.
- [ROADMAP.md](ROADMAP.md) is updated as items land; its Now section reflects
  current work.
- If maintenance ever pauses, a pinned issue will say so. This project does
  not go quiet silently.
