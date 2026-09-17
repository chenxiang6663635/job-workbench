<!-- Confirm before submitting. Items marked * are required. -->

## What does this PR do? *

<!-- One or two sentences. Link issues with Fixes #N -->

## Self-check

- [ ] `pytest tests/` passes (locally or via CI)
- [ ] `python tools/jobws.py lint i18n / ui-tokens / themes / size` green (CI runs all four; `size` = size budget, stock files registered in `tools/size_allowlist.txt`)
- [ ] Frontend changes: `npm run lint` + `npm run build` green; unit tests added/extended under `web/frontend/tests/unit/` where the change is pure logic (`npm run test:unit`)
- [ ] UI changes: `npm run test:ui` passes (layout + a11y smoke; run `npm run build` first — it serves `dist`)
- [ ] **No real personal data**: nothing from `personal/`, no real companies/jobs/names/phones/emails/schools in the diff, screenshots or examples (use `Sample Corp A`, `sample@example.com`)
- [ ] Honest red lines untouched (resume verbs may be questioned; knowledge gaps are never fabricated) - if touched, justify in the description
- [ ] `tools/` changes stayed domain-agnostic (domain knowledge goes into profiles, personal facts stay in `personal/`)

## Dual-track review *

<!-- Both rounds must be recorded as PR comments before merge. Do NOT label self-review as independent review. -->

- [ ] **Round 1 - author self-review**: file-by-file pass over `gh pr diff`, verdict posted as a PR comment
- [ ] **Round 2 - independent review**: a fresh-context reviewer (zero prior context) reviews the same diff, verdict posted as a PR comment
- [ ] MAJOR+ findings from either round are fixed (extra commit) or explicitly deferred to a tracked issue

<!-- Bot dependency PRs (`dependabot[bot]`, patch/minor only) are exempt from Round 2 —
     author self-review + the four CI checks are the gate. Major bumps are NOT exempt.
     See CONTRIBUTING.md §分支策略 → 「例外（机器人依赖 PR）」. -->


## Verification *

<!-- Key commands and output excerpts so a reviewer can reproduce -->

## Notes

<!-- Screenshots (sanitized), trade-offs, known limitations, follow-ups -->
