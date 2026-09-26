# Contributing & Development Workflow

> **This is the full contributor handbook (English).** The short index lives in the
> repository root: [CONTRIBUTING.md](../CONTRIBUTING.md). The Chinese version of this
> handbook is [contributing.zh-CN.md](contributing.zh-CN.md) — the two are kept in sync
> as a pair; when they disagree, the Chinese one is authoritative (the maintainer writes
> in Chinese and the English text is derived from it).

This document defines the development-process constraints of this repository. It applies
to the maintainer (the first user), AI collaborators, and outside contributors.
Data layering and domain rules live in [AGENTS.md](../AGENTS.md); the documentation index
is [docs/README.md](README.md).

## Project positioning (read this first)

- **Self-use first**: the maintainer is the first user. The project is used as the
  strictest real user would use it — but **the maintainer is not the market**. Dogfooding
  answers "is it broken / is it awkward"; it does not answer "does anyone want it".
- **Single maintainer**: the process is built around "minimum viable". Any engineering
  apparatus whose maintenance cost exceeds its benefit is simply not built (see
  "Explicitly not doing" at the end).
- **Local git only, originally**: for a long time there was no remote and no CI; after
  open-sourcing, GitHub Actions runs tests and builds as the quality gate, while
  distribution is still a manually archived installer.

## Privacy rules (in force since open-sourcing — read before contributing)

- **This repository contains no real personal data**: `personal/` is entirely in
  `.gitignore`, and real data was scrubbed from history.
- **Never commit anything under `personal/`**: that includes its file paths, real company
  names, résumé fragments, application records, screenshots.
- **Never commit real identity information**: names, phone numbers, email addresses,
  schools, ID numbers, photos — always use placeholders in docs and examples
  (`示例公司A`, `sample@example.com`, `你的姓名`).
- **Use fake data in examples**: tests and templates keep the existing fake data
  (`13800000000`, `z@x.com`, `示例公司A`) — do not replace it with real information.
- **If you find a leak**: open a **public issue that reports only the location**
  (**do not paste the leaked content itself**); the maintainer will scrub history with
  `git filter-repo`.
- **Two channels, do not mix them**: **personal-data leakage** (a real file made it into
  history) goes through the previous bullet — a public issue that **only states the
  location**; **exploitable security vulnerabilities** go through the private channel in
  [SECURITY.md](../SECURITY.md) (Security → Advisories), and public issues must not
  contain reproduction details (that would put every user at risk first).

## The four gates for a new requirement (walk through them before writing code)

Any new requirement — whether it comes from your own pain point or someone else's
suggestion — passes these four gates first:

1. **How many times has this come up?** (rule of three)
   First time → write a throwaway script or a document, **it does not enter the codebase**;
   second time → turn the hard-coded thing into a configuration item; third time → only
   then generalise it into a feature.
2. **Does it contain personal facts?**
   Anything that belongs to one specific person (the content of a personal-facts file, a
   personal word list, a personal checklist) → it goes into the `personal/` configuration
   layer or a domain profile, and **never into core code**. This gate filters out most
   self-use requirements.
3. **What does generalisation cost?**
   ≤ 1 hour → do it along the way; > 1 hour → just file an issue and record it; do not
   break the structure "because it was easy".
4. **Does it touch the data model or the honesty red lines?**
   Anything that changes the data format, or touches the honesty red lines in
   [AGENTS.md](../AGENTS.md) → it needs its own issue / design note to argue the case;
   **never change it directly because one use case feels urgent**.

**Structural insurance**: one "productisation task" (configuration / documentation /
tests) is carved out every week and pushed separately from self-use work. Without it,
"self-use first" defers productisation forever.

## Branching strategy (tiered PRs + trunk-based)

- `main` is the only trunk. Changes are tiered by **whether they affect runtime
  behaviour** — not by a blanket rule:

**Must go through a PR** (changes that affect runtime behaviour):

- Code changes in `tools/`, `web/backend/`, `web/frontend/`, and `tests/` cases
- Dependency changes (`requirements*.txt` / `package.json`); CI / workflow configuration
- Data-model / schema changes; anything touching the honesty red lines in
  [AGENTS.md](../AGENTS.md)
- PR bar: green CI (backend pytest, frontend lint + build, PR-title check, UI smoke —
  **all four checks must pass; red means no merge**) + a self-check against the
  [PR template](../.github/PULL_REQUEST_TEMPLATE.md) + **dual-track review (both rounds
  are traceable — borrowed from branch closeout's Review Intake clause)**:
  1. **Author self-review**: read through `gh pr diff` file by file (focus: privacy and
     the four gates, API consumption surface, whether the change is purely additive) and
     land the conclusion in the PR with `gh pr comment`;
  2. **Independent review**: dispatch a **fresh-context** subagent to review the same diff
     file by file as a stranger would (without carrying the author's intent — only the
     code itself);
  Both rounds (including the problems found and the decisions taken) must stay on the PR
  page — even a single-developer project must keep the PR traceable as to "what changed,
  what each round found, why it was decided this way". **Never label the author's own
  review as the independent review, and never fake a review identity.** Issues found as
  MAJOR or above in the independent round are fixed on the spot (extra commit) or
  recorded for a follow-up PR — never merged silently (evidence: PR #13's independent
  round caught 3 MAJORs that self-review had missed entirely). Squash and merge; delete
  the branch afterwards.

> **Cross-harness reproduction (since 2026-09-14)**: the second track is not tied to a
> harness — `python scripts/review.py` (it auto-detects a second CLI by default: claude /
> codex) first writes the full `base...head` diff to the repository root
> (`tmp_review_diff.patch`, already gitignored) and then lets the reviewer **read the
> files itself** to produce findings — a large diff never gets truncated by an argument
> size limit. The same prompt works on a CodeBuddy subagent, Claude Code, and Codex.
> Measured: re-checking an already-merged PR across harnesses can be compared against the
> subagent track's conclusions.
>
> **Exception (bot-authored PRs, decided 2026-09-13)**: dependency-upgrade PRs created by
> the official GitHub Dependabot (criteria: the author is `dependabot[bot]` **and** the PR
> carries the `dependencies` label — do not look at the author name alone; it is an
> externally controllable field) **still need the author self-review**, and are exempt only
> from the second, independent round; the bar is author self-review + the four CI checks.
> - Rationale: those diffs are version numbers and lock files, so the second round carries
>   very little information; the real verifier is CI (build, tests, UI smoke), and forcing
>   "two rounds" onto them only produces a rubber-stamp ritual.
> - **Boundary (three conditions, all required)**: ① it covers **patch / minor** upgrades
>   only; **major upgrades do not qualify** (e.g. electron 33 → 44 is 11 majors and must go
>   through a human batch with runtime/desktop smoke — research in
>   `docs/research/report_electron_33_to_44.md`). Criterion: **whether the dependency's own
>   semver major number changes** (a different first segment means major) — not the wording
>   of the PR title, and not the dependency type (dev/prod count alike). ② The Chinese
>   title must still be written (the gate applies as usual; the bot cannot produce a
>   compliant title). ③ The self-review comment must state "what changed + the
>   compatibility judgement" — not just "CI is green".
> - Relation to §Commit conventions: what the exception waives is the **number of review
>   rounds**, not the title-language rule — do not conflate the two.
> - If the bot is swapped (e.g. Renovate) or the author name does not match, the exception
>   **does not apply** (back to two rounds) — the failure direction is deliberately
>   conservative.

**All changes go through a PR** (including text and data-only changes): `main` has branch
protection with `enforce_admins` on — a direct push is rejected at the protocol level; the
required CI checks (backend tests / frontend build / PR title / UI smoke) must all be green
before merging. Historical note: direct pushes of text-only changes were allowed before
protection was enabled (2026-09-08); that rule is void (corrected 2026-09-25 — under
`enforce_admins=true`, direct pushes were never an executable option).

- **Create the branch before you start**: the branch is created before the first line of
  code (`git switch -c feat/xxx`); do not write on `main` first and check out later —
  although uncommitted changes would be carried over and `main` stays clean, the flow gets
  confusing, and if you forget to branch midway, the commit lands straight on `main`.
- **Local commit guardrails (githooks)**: after cloning, run
  `git config core.hooksPath .githooks` to enable them. pre-commit: privacy guardrail
  (`personal/` paths and real phone/email patterns are blocked at the commit entrance) +
  a >1MB file check + **size budget (the same implementation as `jobws lint size`, scanning
  only staged files; the backlog lives in `tools/size_allowlist.txt`)** + a fast pytest run
  (full suite **≈25s** (934 cases measured 2026-09-20); over 60s it names the threshold in
  the output, see "Test size and thresholds" below; when the interpreter lacks pytest it
  degrades to a warning, with CI as the backstop). commit-msg: Conventional format
  `type(scope): subject` (type restricted to an enum, **the subject must contain Chinese**,
  ≤100 characters), with Merge/Revert exempt. The decision logic lives in
  `tools/commit_header.py`, shared with the CI PR-title check. Emergency skip:
  `--no-verify` (explain why in the PR if you use it).
- **The PR title is checked too (CI workflow `pr-title`)**: the local hook only runs when
  *you* type `git commit`, whereas the PR title is what GitHub uses to generate the commit
  subject at merge time — **the local hook structurally cannot see it**, so only CI can
  check this step (language rule in §Commit conventions). `tools/jobws.py lint pr-title`
  reads the title from the `PR_TITLE` environment variable rather than interpolating it into
  `run:` — a PR title is externally controllable input, and interpolating it into a shell is
  an open back door. On violation CI turns red; `gh pr edit <number> --title
  "feat(scope): 中文说明"` fixes it. This workflow is a separate file and explicitly
  subscribes to `edited`, because `pull_request` by default only fires on opened /
  synchronize / reopened — **editing the title does not re-run it by default**, so
  "just follow the hint and fix the title" would not clear the red cross (hit in practice
  on 2026-09-10).
- **Pre-check the title locally before opening the PR (same implementation; saves a
  round-trip in one second)**: `python tools/jobws.py lint pr-title --title "<the title you
  plan to use>"`. CI is the hard gate, but a local pre-check moves "found out the title is
  invalid only after opening the PR" to before you press Enter (measured 2026-09-12: a
  scope written as `feat(api,ui)` — the scope regex rejects commas, both local commits
  passed, and the PR title only turned red in CI).
- **PR granularity is "one independently acceptable batch", not "one commit"**: a branch
  may hold several small commits; open a single PR once everything is done and
  `npm run build` / the tests are green. Example: P1's three page-migration batches = three
  PRs.
- Branch naming (PR path): `feat/<issue-number>-<slug>`, `fix/<issue-number>-<slug>`,
  `docs/<slug>`; lifetime ≤ 1–2 days; delete as soon as it is merged.
- Fallback (what if something goes wrong): a data-snapshot backup + `git revert` — a squash
  commit can be rolled back as a whole without polluting the trunk history.
- Only three situations call for a branch instead of a direct push: an experiment you might
  abandon / a refactor that takes more than half a day / a change that temporarily breaks
  "the currently usable state".
- **No** `develop` / `release` / `hotfix` branches.

## Commit conventions (Conventional Commits)

Format: `<type>(<scope>): <description>`

- `feat` / `fix` / `docs` / `chore` / `refactor` / `data` / `job`: **none of them trigger a
  version bump** — under the timestamp system the version is generated from "the day of
  release" (see §Versioning), and is no longer derived from the commit type.
- Breaking changes: the `!` suffix or a `BREAKING CHANGE:` body section; when landed, write
  it into that version's "Breaking changes" subsection in the CHANGELOG (the version number
  itself no longer expresses breakingness).
- **Data operations are committed separately from code**: commits that enter data into the
  workspace use the `data:` / `job:` prefix and are not mixed with feature commits.
- **Language: the commit subject and the PR title are always Chinese, and so is the body.**
  After a squash merge the PR title **becomes the commit subject on the trunk**, so the two
  are two halves of the same rule — agreeing on commit messages while missing the PR title
  produces the mixed-language result where "the author's local commits are Chinese but the
  merge into the trunk is English" (evidence: the English titles of PR #15 / #16 landed on
  `main` as `53e7b04` / `b774cce`, sandwiched between Chinese commits). Subject and title are
  machine-checked by the hook + CI (see §Commit flow); **the PR body is not machine-checked**
  — it necessarily contains code blocks, type enums, and English terminology, and a machine
  judgement would only produce a noisy gate that people bypass or complain about; that part
  is left to the dual-track review. The English headers in the issue / PR templates are
  **fill-in hints** for outside reporters, not a language requirement for the body; the
  English README / docs aimed at English readers are a separate matter.
- **Merge method**: `main` has `required_linear_history`, so only squash and rebase are
  available. **Use squash** — rebase would lay every original subject from the branch onto
  the trunk verbatim, completely bypassing the PR-title gate (the local commit-msg gate
  would then be the only interception point).
- **Delete the branch as soon as it is merged (both sides) — do not let them pile up.**
  During the 2026-09-16 cleanup, **26 already-merged branches** had accumulated locally
  (and 8 more on the remote); the root cause is a side effect of squashing — **squash
  rewrites commits, so a branch's ancestry never matches `main` again**, and
  `git branch --merged main` recognises none of them while `git branch -d` refuses too,
  making them look like "these branches are still useful". In reality all of them
  correspond to merged PRs.
  - **Only one criterion is trustworthy: the PR record** (`merged: true`) — not `--merged`,
    and not `git rev-list main..<branch>`. The cleanup script `tools/branch_audit.py` uses
    exactly that (look up the PR by branch name → read `merged`; only when there is no PR
    does it fall back to "is the head subject already on main"). **It only reports, never
    deletes** — it prints three groups ("safe to delete / needs a human decision / keep"),
    and the deletion itself is a human decision:
    ```bash
    python tools/branch_audit.py          # read the report first
    git branch -D <branch> [...]          # delete after confirming
    ```
  - **Remote**: the repository has `delete_branch_on_merge` enabled, so merging deletes it
    automatically. To delete manually: `git push origin --delete <branch>`.
  - **Local**: after merging, `git branch -D <branch>` (`-D`, not `-d` — as noted above,
    `-d` necessarily misjudges a squashed branch as "not merged").
- **Two paths this gate cannot catch (known gaps — do not treat it as omnipotent)**:
    1. **Manually editing the final commit message in the squash dialog**: that changes
       neither the PR title nor triggers `edited`, so the check does not re-run — an English
       subject lands on `main` just the same. It is mechanically unstoppable (the
       `pull_request` event cannot see the text you type at merge time), so the rule is
       **do not touch the default commit message when merging**.
    2. **A check script that ships in the same PR as the thing it checks**: both the
       workflow and `tools/*.py` come from the PR's own branch, so a PR can loosen the
       judgement (change the CJK regex to `.*`) and CI still stays green. A single-developer
       repository has no second approver; the practical defence is the behaviour pinned in
       `tests/` — loosening the regex turns that suite red immediately. **When you change a
       judgement rule you must change the tests in the same commit and state the reason**;
       that is the only way this defence works.

## Versioning (month-granularity CalVer `YY.MM.N`, since 2026-09-24)

Semantic versioning is retired (the 0.x minor/patch mapping and the `v1.0.0` wording are
void along with it). Current rules:

- **Single form (since 2026-09-24)**: the version is **month-granularity CalVer `YY.MM.N`**
  (e.g. `26.9.0`) — the tag, the CHANGELOG section name, the `version` in
  `web/electron/package.json`, `latest.yml`, the artefact filename, and the "About" block in
  the UI **are all the same number** (there is no longer a "release number / machine
  version" pair of forms).
- **The third segment `N` = which release of the month** (starting at 0): the first is
  `26.9.0`; a hotfix **keeps the first two segments and only moves the third**
  (`26.9.1` — under electron-updater semantics that is the only bump that triggers an
  update: an `-rc` suffix is judged older and a `+N` suffix takes part in equality, so
  neither triggers); a second release in the same month keeps incrementing (`26.9.2`); a new
  month resets to zero (`26.10.0`).
- **Why it had to change (measured evidence)**: electron-updater's version comparison goes
  straight through Node semver — four segments (`26.9.15.1`) and zero-padded months
  (`26.09`) are both **invalid** (`semver.valid` → null; comparison throws a `TypeError` or
  simply skips the tag), which voids the old pair of forms as well; the month-granularity
  three-segment form is valid semver and has precedent in Bitwarden Desktop (`YYYY.N.P`).
- **Generation**: `python tools/jobws.py release version` prints the number for "a release
  this month" (it reads the `git tag` sequence and increments N when the month already has a
  tag; it writes no state file). **Writing it into `package.json` is still a manual bump**
  (step 2 of the release process); `release check` is the gate.
- **Single source of truth**: the `version` in `web/electron/package.json`; there is no
  second source.
- **Tag convention**: `v<version>` (e.g. `v26.9.0`); **the CHANGELOG section name = the
  version**. Tag-to-version comparison = **character-for-character equality**
  (`release_assist.version_matches_tag`, same implementation locally and in CI).
- **Breaking changes**: no longer carried by the version number — write them into that
  version's "Breaking changes" subsection in the CHANGELOG plus an "upgrade notes" preamble
  (impact and migration steps).
- **Release discipline (since 2026-09-15)**: **a single release point** — intermediate
  batches do not bump / tag / create a Release / build an installer; everything is released
  once after all batches are done.
- **Other `version` fields (private / independent packages, not part of releasing)**: the
  `version` in `web/frontend/package.json` and `mcp/pyproject.toml` are private to those
  packages and **must not be tied to the release number**; `.codebuddy-plugin/marketplace.json`
  has no version field. **Exception (a derived artefact, not a source of truth)**: the domain
  package `packages/jobws-core` reads its version at **build time** from its own `setup.py`
  out of `web/electron/package.json` and writes it into the wheel metadata, reading it back
  at runtime from `importlib.metadata` (CI asserts the three agree, see
  `jobws_core/_version.py`). It is likewise **not** a source of truth — changing the version
  still means changing `package.json` alone; do not edit the package's `pyproject.toml`.
- **Contemporary reference**: the tag sequence from `v0.1.0` (2026-09-08) to `v0.3.2`
  (2026-09-14) is the semantic-versioning era; the `v26.09.15.1` period (the 2026-09-15
  system, **which never actually published a tag**) is void; **the next version is
  `26.9.0`** (the first month-granularity number of 2026-09); the actual value is always
  whatever `web/electron/package.json` and `git tag` say.

## CHANGELOG style (single file, two levels, since 2026-09-20)

For an outside release the CHANGELOG is the reader's first stop, so the style is constrained
by "written for humans to read" (a Keep a Changelog implementation, informed by the actual
shape of projects such as Tailwind and Ant Design):

- **Two levels per version section**: the section opens with `### Highlights (English)`
  (3–5 lines of English summary — **English commits to a summary only, not to every entry**)
  and `### 看得见的变化` (3–5 plain-Chinese bullets: verb first, one thing per bullet, with
  the PR / issue number at the end of the line); below that, `### 技术细节` collects the raw
  detailed notes (historical text is not rewritten).
- **Internal engineering entries go to the `Infrastructure` section only** (CI / tests /
  size budget / refactors / packaging / scripts / documentation proofreading); that section
  keeps the fixed preamble "does not affect usage, this is an internal quality improvement".
  Criterion = **whether it changes the user-visible behaviour of the distributed software**.
- **No naked terminology**: a newly introduced internal term is either explained in one
  sentence right there, or added to `docs/glossary.md` and linked from the entry.
- **Version sections must be self-consistent**: entries in reverse-chronological order; the
  bottom compare references filled in (pointing at real tags); `[Unreleased]` is the
  accumulation area before a release and becomes the release number + ISO date at release
  time (see §Release process).
- **Historical sections stay as they are** (0.3.2 and earlier): only add the note "this
  section is the original detailed record; the format is unified from the next version on" —
  do not backfill.

## Release process (manual archiving)

Tag from `main`, never release from a branch (**a single release point**: no releases in
between, see §Versioning):

1. **Smoke verification** (CI has already run the full automated suite; a manual smoke is not
   optional): run the build script to produce the installer → **install and run it once** →
   open the eight pages with your old data and operate each one; for UI-related batches,
   accept by screenshot comparison (you must be able to point at visible differences).
2. **Generate the current month's number and bump the version**:
   `python tools/jobws.py release version` to get "the release number for this month"
   (`YY.MM.N`) → write that same number into the `version` field of
   `web/electron/package.json`.
3. Change the `Unreleased` section of [CHANGELOG.md](../CHANGELOG.md) into the **version
   number** + ISO date (the section name is the tag name).
4. **Local pre-check before tagging**: `python tools/jobws.py release check --tag v26.9.0` —
   it verifies the tag and the version are **character-for-character equal**, that the
   CHANGELOG has that version section, and previews the release notes to be published (the
   same implementation as CI; do not tag while it is red).
5. **dry_run rehearsal**: `gh workflow run release.yml -f dry_run=true -f tag=v<version>`
   (it produces the exe + `latest.yml` and the notes without touching the Release; the `tag`
   input is used to check the CHANGELOG section and version comparison — **run it after step
   3 has landed**) → once it passes, `git tag -a v<version> -m "..."` and push.
6. After release, verify with `gh release view --json assets` (the installer + `latest.yml`
   are both there) and **download the artefact once for real**; archive the build output by
   release number to a directory outside the repository (artefacts are already excluded by
   `.gitignore`).

**Hotfix**: fix-forward — open a `fix/` branch, go through a PR into `main`, then release
with the current month's number (**keep the first two segments and only move the third**;
N increments; a new month restarts from 0). Do **not** branch a hotfix off an old tag.

**Withdrawing a bad release**: re-release with a **higher** version number (increment N for
the month is enough); re-releasing the same version name does nothing — electron-updater will
not accept an identical or lower number overwriting it (details in the RUNBOOK in
`docs/release-checklist.md`).

**Auto-update**: the Windows packaged build **has it enabled** (electron-updater, since
v0.2.1; the trade-off of an unsigned update chain is recorded in SECURITY.md); first
distribution still goes through a manual installer; **macOS auto-update is not done** (the
remaining blocker is code signing, which the OS requires). The `personal/` privacy strip is
done (entirely gitignored + `git filter-repo` history scrub).

## Release governance (blocking list / freeze window / tiered verification)

**Release blocking list** — meeting **any** of these means no formal release (these eight
are treated separately from ordinary P1/P2; there is no "fix it next batch" option):

1. Data corruption or silent overwriting;
2. Secret / credential leakage;
3. Path-escape class security problems;
4. The installer cannot install or start;
5. A broken update chain (`latest.yml` / auto-update path broken);
6. Main-flow blockage (crashes on open, a core page unusable);
7. Privacy wording inconsistent with real behaviour (`docs/data-flow-matrix.md` is the
   authoritative source);
8. Unreliable backup / restore — "it can produce a zip" does not count; only a verified
   restore counts.

Four of them **do not wait for a feature batch** and can go straight to a `26.9.N` hotfix
(the 2026-09-25 addendum to the `ship-once-per-release` ADR): **security vulnerabilities /
data corruption·silent overwriting / install·startup blockage / broken update chain**.

**Release freeze window (RC stage)**: from the moment a release intent is fixed (number
taken / section landed) until the tag, `main` accepts release-blocking fixes only, and
everything else queues for the next `N`. The standard moves in the window: dry_run rehearsal
(the full release.yml chain, including a forced full E2E) → real-machine smoke (section 2 of
`docs/release-checklist.md`) → tag. **No rc tag is actually published**, but the window
discipline is followed as written.

**Tiered verification (Tier 1/2/3)** — verification responsibility deepens by tier:

- **Tier 1 (every PR)**: full pytest + the seven scanners + frontend lint / tsc / unit tests
  + UI smoke (smoke / viewports / a11y / nav);
- **Tier 2 (after landing on main)**: the full 115-case E2E suite (the `e2e-full` job runs
  automatically) + the domain-package standalone install smoke + the exe smoke;
- **Tier 3 (at release)**: the full release.yml chain — forced full E2E, install/uninstall
  smoke, SHA256, and a real-machine manual smoke.

**Outbound-network update discipline**: before adding any networking feature, **first**
update `docs/data-flow-matrix.md` (and the matching privacy wording in the UI), **then**
change the code — a PR that adds outbound traffic without updating the matrix should be
rejected in review (see the "governance rules" section of the matrix).

## Sustainability commitments

- **Make the time box public**: the README states the **shape of the investment** (in
  batches — a few days of focused work, or a whole week with nothing; outage windows below)
  and the **response target** (first reply to an issue within 48 hours, slips disclosed, see
  `docs/maintenance.md`); **no throughput numbers** — the number of PRs fluctuates with
  tooling and batches and is not a stable promise (corrected 2026-09-20).
- **Outage windows**: no development during interview weeks / written-exam weeks — the
  project serves the job hunt, it is not the opposite of it.
- **Issue cap**: once unhandled issues exceed 30, triage and close to prevent a backlog
  paralysis.
- **Vision first**: major directions get a design note first (`docs/specs/`), so that people
  can leave and the vision keeps the project moving.

## For AI collaborators

- This document and [AGENTS.md](../AGENTS.md) are complementary: this one governs
  "process", AGENTS.md governs "data layering and honesty red lines" — they do not repeat
  each other.
- AI changes are subject to the four gates just the same; when a requirement cannot reach
  the third gate, suggest downgrading it to a throwaway script or `personal/`
  configuration.
- Run the verification (scripts / lint / tsc) before committing; never write "it should run"
  into a commit message.
- **Local verification chain (the same as CI)**: `pip install -r
  web/backend/requirements-dev.txt` → `python -m pytest tests/ -q` (**≈42s / 1455 cases — the latest re-check, i.e. the current
  value** (2026-09-25: 1455 passed + 14 skipped; the 60 MCP-side cases in `mcp/tests/`
  run separately); check that the case count was not accidentally under-collected) →
  **before committing run `python tools/jobws.py lint {i18n,ui-tokens,themes,four-ends,size}`**
  (the first three already run in CI; `size` is the size-budget gate added 2026-09-16 — when
  over the limit, split it or register it in `tools/size_allowlist.txt` with a stated reason;
  never bypass it silently; `four-ends` is the four-end consistency gate added 2026-09-17,
  see the next bullet) → frontend `npm run lint` + `npm run build` (use `npm.cmd` on
  Windows) → **if you changed pure logic (class-name merging, formatting, fallback branches),
  add cases to `web/frontend/tests/unit/`** (`npm run test:unit`, Vitest; it deliberately
  pulls in no jsdom and only collects `tests/unit/**`) → **for UI changes also run
  `npm run test:ui`** (layout + a11y smoke; needs `npm run build` to have produced `dist`
  first, and the demo workspace to exist: `python tools/jobws.py init --target demo --demo`).
- **Test size and thresholds (since 2026-09-20)**: the three suites are counted **separately**;
  do not stare at the pytest total alone (the fastest-growing one is actually e2e).
  - Baseline (measured 2026-09-24): pytest **97 files / 1352 cases (+10 skipped) / ≈40s for
    the full suite locally** (the pytest job in CI takes about 40s and is **not on the
    critical path**); vitest **22 files / 172 cases** (`web/frontend/tests/unit/`); Playwright
    **17 specs / 115 cases** (**split on 2026-09-25**: the PR `ui-smoke` runs only the minimal
    set smoke + viewports + a11y + nav (`npm run test:ui:smoke`), while the full 115 run in the
    `e2e-full` job after a push to main — it does not block PRs and regresses right after the
    merge); MCP **7 files / 61 cases** (`mcp/tests/`, run separately from pytest). The order of
    magnitude of each CI job's **duration** (it floats with the case count; read the current
    number on Actions): UI smoke (PR minimal set) ~100s / **e2e-full (main push) ~170s** /
    backend exe smoke ~90s / frontend build ~30s / MCP ~24s / domain package ~14s.
  - **These numbers move with the batches**: the figures above are **measured snapshots**, not
    a contract — after changing code, trust your own local run; when a figure is far off, fix
    it here as you go (never write "it should run N cases").
  - Action thresholds: **local full suite > 60s, or the hook feels > 30s → first give the hook
    / local run pytest-xdist (`-n 4`, no coverage loss; do not use `auto` on a 32-core
    machine)**; CI pytest job > 3 minutes → parallelise further on the CI side; **total CI time
    > 5 minutes → look at e2e-full and the backend exe smoke first (currently ~170s / ~90s;
    the PR ui-smoke is about 100s after the split), not pytest**; only above 10 minutes does
    sharding / filtering become a conversation.
  - Explicitly not doing: ① making the hook run "the subset related to the change" — this
    repository is coupled across layers (domain layer → CLI → backend → frontend) and has no
    module→test mapping, so missing a run means a false green; ② filtering UI smoke by path —
    there is precedent of a backend change turning UI smoke red; **implemented on 2026-09-25
    by "splitting jobs"** (the minimal set on PRs, the full suite in `e2e-full` on main push),
    no longer by squeezing `--shard`.
  - xdist prerequisites: a new dependency in `web/backend/requirements-dev.txt` (goes through a
    PR as usual; CI installs it too); verify parallel safety first (the tests' `file_lock` and
    `pathres.snapshot_root()` must land in tmp).
- **Install the domain package before developing (since 2026-09-17)**: `uv pip install
  --python <3.12 interpreter> packages/jobws-core` (a venv created by uv usually has no pip;
  `<interpreter> -m pip install packages/jobws-core` also works). It also runs without
  installing — the legacy-path shim degrades to source form (adding
  `packages/jobws-core/src` to `sys.path`) — but that is not the target shape: the target is
  **works as soon as it is installed**, and CI guards this with a non-editable install smoke.
  **Packaging must use a non-editable install** (`scripts/build_backend_exe.ps1` enforces it).
  - **When moving a new module into the package**: the static module map of a non-editable
    install cannot see **new files**, so without reinstalling you get a `ModuleNotFoundError`
    (measured 2026-09-19, A-1). For local development prefer
    `uv pip install -e packages/jobws-core --config-settings editable_mode=compat` — compat
    mode puts the whole `src` on the path so new modules become visible automatically.
- **`jobws lint legacy-imports` (added 2026-09-17)**: counts legacy-name import sites, with a
  list (`tools/legacy_imports_allowlist.txt`) as a **monotonically decreasing** budget. New
  code always uses `jobws_core`; **when the budget reaches 0, delete the shim** — `filelock` /
  `workspace_io` completed this on 2026-09-19 (18 sites renamed + two shim files deleted);
  `tracker` / `approval` / `pathres` are the budget registered after the second package move
  (PR-B keeps pushing it to 0). After the names are cleared they stay in `LEGACY_NAMES` as a
  **firewall**: whoever writes the old name again is stopped on the spot instead of silently
  adding another legacy path.
- **Interpreter baseline 3.12 (since 2026-09-14, previously 3.8)**: CI, packaging and docs all
  treat 3.12 as the baseline. The technical requirement is really only ≥3.9 (for `imaplib`'s
  `timeout=`), but the only version **supported** and verified is 3.12 — so `tests/conftest.py`
  stops anything lower before collection: tests on the wrong interpreter are **silently
  untrustworthy**, and that kind of failure looks like "the code is broken". The most common
  trap on this machine is `python` resolving to a conda environment another project is using
  (3.8), so run `python -V` first.
  - **The interpreter for the pre-commit fast run**: the hook resolves in the order
    `JOBWS_PYTHON` > the repository's `.venv` > the interpreter running the hook; when it
    resolves to something below 3.12 it **degrades to a warning instead of blocking the
    commit** (that conclusion would be untrustworthy; CI is the backstop). The maintainer
    recommends setting it once: `setx JOBWS_PYTHON "<a 3.12 python>"`.
  - **`web/start.ps1` resolves the backend interpreter in the same order** (and additionally
    verifies dependencies: it only counts if `import fastapi, uvicorn` succeeds), **so it does
    not depend on which environment the terminal has activated** — a terminal that
    auto-activates conda base (or another project's environment) no longer affects starting
    this repository; `.\start.ps1 -CheckOnly` only does the pre-check and prints which
    interpreter it would pick. **A user-level `JOBWS_PYTHON` saved with `setx` is read too**
    (`setx` only applies to new terminals; the script catches the "just set it but the
    terminal has not refreshed" case for you and prints a hint).
  - **Environment convention**: use a 3.12 venv with
    `web/backend/requirements-dev.txt` installed. **It can live inside the repository
    (`.venv/`) or outside it** (both are in `.gitignore`; the hook and `start.ps1` both prefer
    a `.venv` inside the repository, which is the least trouble). Measured size ≈98MB — it
    does not affect git (already ignored) but makes the **full test suite go from 12s to 216s**
    on Windows (measured 2026-09-14: file scanners walk `site-packages`). **If that is too
    slow, put it outside the repository** and point `JOBWS_PYTHON` at it; **do not touch conda
    or the system Python** (they are other projects' homes), and do not install global pip
    packages.
  - **Dependency upper bounds were relaxed on 2026-09-16** (pinned in the 3.8 era; gradually
    lifted after the baseline moved to 3.12): now `fastapi<0.142` / `pydantic<2.14` /
    `pypdf>=6.18.1` (`uvicorn<0.53` untouched). Relaxing is not a one-off action but **measured
    one at a time** — each item is only merged after installing the new version and running the
    full regression (PR #109 / #127 / #129). Measurement record: with `fastapi 0.141.1` +
    `starlette 1.6.0` + `pydantic 2.13.5` + `pypdf 6.19.0`, all 679 cases passed (the count at
    the time, 2026-09-16; now 934); **crossing a starlette major version (0.46→1.6) was fine**.
    Two items are still stuck (**major; need a migration batch first**):
    `@vitejs/plugin-react` 6.x wants `vite ^8` (the repository is on vite 6.4.3), and
    `typescript` 7.x is not supported by typescript-eslint (`npm run lint` fails outright).
    Both are recorded in `.github/dependabot.yml` with their expiry conditions, and
    **deliberately carry no `ignore`**.
  - **After changing dependencies you must run `npm run lint` / `tsc` / `vite build`**:
    `npm install` exiting 0 **does not mean it is usable** — the typescript 7 case installs
    fine but eslint throws at runtime. Running only the install leads to the wrong conclusion.

## Developer tooling (MCP / code graph — for developers and AI, not the product)

The project distinguishes **product runtime dependencies** (what an end user needs to run it:
a browser + Chrome + the `tools/` scripts + the web layer) from **development aids** (tools a
developer leans on while writing code: GitNexus impact analysis, CodeGraph code graphs,
Playwright for clicking through pages). The former live in the repository and ship with the
project; the latter belong to the **developer's personal environment** and do not enter the
product path. Hence "CONTRIBUTING mentions GitNexus/Playwright" and "the product does not
include them" are not in conflict.

To use the code-graph tools while developing in this repository: the index is a **per-repository
runtime artefact** already excluded by `.gitignore` (`.gitnexus/`, `.codegraph/`); after a
clone / machine change, rebuild it once:

```
powershell -ExecutionPolicy Bypass -File scripts/index_dev_tools.ps1
```

This assumes `gitnexus` and `@colbymchenry/codegraph` are installed globally (`npm i -g ...`).
An MCP declaration sample is in `.codebuddy/mcp.example.json` — copy it to your user-level
`~/.codebuddy/mcp.json` and replace the path placeholders.

**Privacy reminder**: `personal/` has been scrubbed out of the repository at open-sourcing,
but the local workspace's `personal/` still holds real data (résumé, contact details). The
code-graph index records some file names / symbols into `.gitnexus/` / `.codegraph/` (local
caches). Those two directories are gitignored and never enter the repository, but **do not
send them anywhere either**; check index progress with `gitnexus list` / `codegraph status`.

Note: on product PRs there is **no full** Playwright E2E (only the minimal UI smoke, pinning
layout and serious/critical a11y; **the full 115 cases run in the `e2e-full` job after a push
to main**, split on 2026-09-25); **manually clicking through a page with Playwright while
developing** is not covered by that rule and is not restricted.

## Four-end consistency (must be synced when adding a capability)

The same capability working in **four entrances — command line / AI host (MCP) / editor
plugin / desktop UI** — is a design premise; the contract source of truth is
`tools/four_ends_matrix.json`, and the human-readable comparison page `docs/four-ends.md` is
generated from it.

- **The three steps of a change**: implement (domain layer) → register in the matrix → run
  `python tools/jobws.py lint four-ends --write` to regenerate the page. Miss any step and
  `python tools/jobws.py lint four-ends` names it (the matrix says something that does not
  exist, something exists but is not registered, the page is out of sync, or a skill mirror
  disagrees with its source — all caught).
- **Naming and pairing rules** (the ones the checker enforces): MCP write tools are named
  `preview_<action>_<resource>`; writes are always two-phase (command line `--preview` →
  `apply`; AI host `preview_*` → `apply_approval`; the UI relies on a confirmation dialog);
  plugin commands must be registered in the `commands` field of
  `.codebuddy-plugin/plugin.json`.
- **Alignment is additive by default**: existing command names and parameters are a contract
  (see `skills/jwb-cli-contract`), and renaming is a breaking change — add what is missing,
  name new things by the rules, and merely register existing ones in the matrix.
- Distributing assets to the harnesses: `python tools/jobws.py skills install` — since batch 10
  it distributes **three kinds of assets** at once (skills / commands / subagents; the landing
  points are documented in the script header; `--link` is experimental and needs developer mode
  on Windows). **Zero-clone channels** (plugin marketplace install, `npx skills add`) are in
  the README "Quick start"; **the in-repository project-level copies** are compared item by
  item, per asset type, by the checker above (user-level `~/.agents/skills/` and plugin-market
  caches are out of its sight — they do not travel with the repository, see
  [`docs/support-and-compatibility.md`](support-and-compatibility.md)).

## Copy & i18n (UI strings always go through `t()`)

- **All UI copy goes through `t()`**: add keys to
  `web/frontend/src/i18n/locales/zh-CN.ts` (the source language, the single source of truth for
  keys); `en.ts` uses `satisfies Record<TranslationKey, string>` to pin the two key sets
  together **at compile time** — one extra, one missing, or one typo fails the build (no human
  vigilance required).
- **Four things are not translated**: code comments (Chinese comments are this project's
  documentation convention); domain data (stage / batch / round / direction / terminal-state
  enums, CSV column names, Chinese field names in the API — they are the same literals as
  `tools/jobws.py track` and the workspace files, and translating them would desynchronise the
  UI from your history and the CLI); the user's own content; real file and directory names in
  the workspace (keep them as they are, or split the key and sandwich them in the middle).
- **One convention for loanwords in the Chinese UI**: Chinese first, with the original in
  full-width parentheses — `服务地址（Base URL）`, `API 密钥（API Key）`, `模型服务（Provider）`;
  protocol and format abbreviations (IMAP / CSV / JSON / PDF / JD / URL, etc.) keep their
  original form and are not force-translated. **The same word is written the same way across
  the codebase**; error strings, buttons and hints change together, not one at a time (unified
  on 2026-09-14, see [#77](https://github.com/chenxiang6663635/job-workbench/issues/77)).
- **Container components take their copy from the caller**: e.g. `FormField`'s label/hint —
  hard-coding a default Chinese sentence inside the component counts as hard-coding too
  (`emptyLabel ?? t("…")` is the correct form).
- **Module-level constant tables cannot call `t()`**: store `labelKey: TranslationKey` instead
  (`import type { TranslationKey }`) — the type annotation is the compile-time guardrail, and
  the rendering site calls `t()`.
- **The backend does not guess the language**: throw `ApiError(status, code, detail, **params)`
  (`web/backend/apierror.py`); `detail` keeps the original Chinese (both debugging and issues
  read it), and the UI copy is looked up by the frontend from the `err.<code>` message catalog,
  falling back to `detail` when missing. Code naming is `<domain>.<semantics>` and **the same
  semantics must reuse the same code**; user-visible dynamic values (stage names, directory
  names, ids) go through `params` and are never hard-coded in the copy. **Unexpected exceptions
  have a backstop too**: the global handler in `main.py` turns any uncaught exception into
  `server.error` + a readable detail (the full traceback goes to the log) — a bare
  `Internal Server Error` never reaches the UI (hit in practice 2026-09-15: when the backend was
  started with a too-low interpreter, an `imaplib` `TypeError` was caught by no layer at all).
- **Automated check**: `python tools/jobws.py lint i18n` (runs in CI, always available locally;
  it blocks on a hit). It checks four classes of problem at once, whose common trait is that
  **the UI would show a raw key name or a word in the wrong language, and neither tsc nor lint
  can see it**: ① hard-coded Chinese; ② a plural key missing its `count`; ③ a `t()` key that
  does not exist; ④ **hard-coded English** (the reverse blind spot: English appearing in the
  Chinese UI — bare JSX text outside `t()`, `title`/`aria-label`/`alt`/`placeholder` literals,
  and the Electron window/dialog copy keys). The scope of ④ is defined by `EN_SCOPE_RELS` in the
  implementation — `web/frontend/src/pages/**`, `web/frontend/src/components/**`,
  `web/electron/**` (widened from pages to components on 2026-09-14: change the constant, do not
  rewrite the traversal); the Electron main-process catalogs `web/electron/i18n.js` and the
  frontend catalogs are exempted by path in the same way. The narrow scope is deliberate (false
  positives make people start stuffing fake entries into the allowlist, and the check then dies);
  **before widening the scope, do a dry run with `--list` and classify the false positives**. The
  forms it **deliberately does not cover** and its **known boundaries** (a false hit after a line
  comment is not checked, attribute literals inside block comments are not checked, attribute
  values spanning lines are not checked, bare text ending in `;` is always skipped as code, and
  only `title`/`aria-label`/`alt`/`placeholder` plus the Electron `title`/`message`/`detail` are
  covered) are written in the same implementation comment; do not read "the check passes" as
  "no English remains".
- **Allowing data-shaped hits**: register them in `tools/i18n_hardcode_allowlist.txt`:
  `path = fragment1|fragment2  # reason`; **English hits go in the `en:` section**
  (`en:path = fragment  # reason`) — the two allowlists are not interchangeable, and writing in
  the wrong section is the same as not writing it; the prefix **must be lowercase**. The same
  file may be registered on several lines (each with its own reason), and parsing **merges**
  them. **Only the listed fragments are allowed, never a whole file** — a whole-file exemption
  once let 4 untranslated strings hidden in an already-translated file (column headers, diff
  labels, button tooltips) pass green. The list is a "snapshot of the present": when a Chinese
  sentence gets translated or a file is deleted, the entry must be deleted too, otherwise the
  script reports "the fragment no longer appears / the file has no hit" (leaving it would
  pre-authorise a future Chinese string with the same name). To regenerate a draft:
  `python tools/jobws.py lint i18n --print-allowlist`; the reasons are written by a human.
- **Verification**: after changing the frontend run `npx tsc -b` + `npx eslint .`; leave
  `npm run build` to CI (a local vite run rewrites hundreds of files in `dist/`).

## Code hygiene (borrowed from an anti-shit-mountain checklist, trimmed to six clauses)

Self-check while writing; re-check during PR self-review:

1. **Size budget** (measured automatically by `jobws lint size`; the backlog is registered in
   `tools/size_allowlist.txt`):
   - **Logic type** (business code): a file ≤300 lines; a single function ≤60 lines,
     **> 80 must be split** into "an orchestrator + ≥2 helpers"; nesting ≤3 levels.
   - **Data/declaration type** (i18n catalogs, constant tables, tests and fixtures): ≤1500
     lines — that kind of code has many lines and low complexity, and the same threshold as
     business code would only force people to shatter constant tables. The classification is in
     `classify()` in `tools/check_size.py` (recognised by path; declarative blocks inside
     scripts are not listed separately and still count as logic type).
   - **Backlog exempt, increments gated**: files already over the limit are registered in
     `tools/size_allowlist.txt` (`path = lines  # reason`), and **the registered value is the
     water line** — it may only go down, never up; when it drops within the threshold the checker
     demands deleting the entry (self-cleaning, to stop the list from rotting). **New files are
     never allowed to exceed it.**
2. **Extraction timing (rule of three)**: consider extracting the second time the same logic
   appears; the third time it must be extracted into a shared module; when a third `if/elif`
   branch appears with each branch >10 lines, extract a dispatch.
3. **No silent error swallowing**: `except Exception: pass` and empty `catch {}` are forbidden —
   at least log (`logger.warning` / `console.error`).
4. **Single source of truth**: the same enum/mapping/constant is defined in exactly one module
   and referenced elsewhere — a second inline copy is collapsed back to the registry.
5. **All runtime product code must be covered by at least one structural check** (a principle
   settled in the 2026-09-25 closeout batch): `.py / .ts / .tsx / .js / .mjs` × `tools/`,
   `packages/`, `web/backend/`, `web/frontend/`, `web/electron/`, `mcp/`, `scripts/` — the size
   gate previously missed `web/electron` and `.js` (the 967-line `main.js`, the code closest to
   the user's machine, had zero governance); it is now covered. **When adding a runtime code
   directory or suffix you must sync `SCAN_DIRS` / `SOURCE_SUFFIX` in `tools/check_size.py`.**
6. **Two channels for failure paths** (2026-09-25 closeout batch): problems such as a failed
   start, a backend crash, a failed update or a failed restore must have **both** a user-visible
   message and a local structured log; the diagnostics bundle fields are fixed (version /
   platform / log tail) and **always exclude** résumés, mail, API keys, passwords and workspace
   content (`web/electron/diagnostics.js` plus tests pin this down).

> Source: borrowed from the anti-shit-mountain checklist of thermal_comfort_code, trimmed to
> this repository's scale (its dual-threshold transition system and L1/L2/L3 tiers are not
> carried over).

## Explicitly not doing (over-engineering)

`develop`/`release`/`hotfix` branches, semantic-release, a GitHub Projects board, requirement
voting tools, a complex label system, a standalone roadmap site, **a full** Playwright E2E
suite on PRs (narrowed on 2026-09-13 to "no full suite on PRs, only a minimal smoke", and split
on 2026-09-25 into "minimal set on PRs + full suite on main push": the PR gate in
`web/frontend/e2e/` only pins "the page opens / no horizontal overflow / the top bar does not
wrap / no console errors / zero serious+critical a11y issues", while the full 115 cases run in
the `e2e-full` job after a push to main. Rationale: this class of layout breakage has happened
twice in practice — English labels blowing up the top bar, and the window title being
overwritten by the page title — and tsc, eslint and both judgement scripts cannot see it, so
only a real run can), code signing.

(Basis: `docs/research/report_dev_workflow.md` — the minimum-viable trade-offs of a
single-maintainer project. Exceptions: minimum CI (live since 2026-09-08, pytest + frontend
build), minimum UI smoke (live since 2026-09-13, layout + a11y, see the parenthesis above);
**branch protection (enabled since 2026-09-08)** — linear history + force-push disabled
(including for admins). GitHub branch protection cannot distinguish "code vs docs" by path
(required checks forbid all direct pushes as a side effect), so the tiering is upheld by the
rules in the "branching strategy" section, with `revert` as the fallback when something slips.)
