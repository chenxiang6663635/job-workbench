# Maintenance

How this repository is maintained. Written down so expectations are explicit —
for contributors and for anyone evaluating the project's health.

## Release cadence

- Releases are cut when there is something meaningful to ship, typically every
  1–3 weeks. No fixed calendar.
- Versioning: **timestamp**, not semver — release number `YY.MM.DD.N` (tag and
  CHANGELOG section name), machine version `YY.M.D` (`web/electron/package.json`,
  artifact name, `latest.yml`, and the About card in the UI). The full discipline
  lives in [CONTRIBUTING.md](../CONTRIBUTING.md).
- Every release gets a changelog entry ([CHANGELOG.md](../CHANGELOG.md)) and
  GitHub release notes.
- **Before tagging**, run `python tools/jobws.py release check --tag v26.09.15.1`
  locally: it validates the tag/version match (date triple) and the CHANGELOG
  section, and prints the release notes CI will publish (same implementation).
- Releases are cut once, at the end of a plan cycle — intermediate branches are
  merged without bumping, tagging, or building an installer.

## Issue triage

- **First response within 48 hours** — even if the answer is just
  "reproduced, will look into it" or "need more info". When that target
  slips, it is said so in a pinned issue.
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

- Work is bursty and usage-driven: small single-theme PRs in focused batches —
  some days land a batch, some weeks land none (interview / exam weeks are
  off). No unrelated-change dumps, no performative activity. The stable
  commitment is the **response time** above, not a throughput number.
- [ROADMAP.md](../ROADMAP.md) is updated as items land; its Now section reflects
  current work.
- If maintenance ever pauses, a pinned issue will say so. This project does
  not go quiet silently.
