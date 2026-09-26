# Contributing & Development Workflow

> **What this file is.** The contributor handbook is written in Chinese
> ([contributing.zh-CN.md](contributing.zh-CN.md), **authoritative**). This English file is a
> companion with a **two-level commitment**:
>
> - **Full sections** — positioning, privacy rules, the four gates, branching/PR flow,
>   commit conventions, four-end consistency, copy & i18n, code hygiene, explicit non-goals,
>   sustainability. These carry the rules in full and are kept in sync with the Chinese text.
> - **Summary sections** — versioning, CHANGELOG style, release process, release governance,
>   AI collaborator notes, developer tooling. Each opens with a `Summary tier` line; the full
>   rules — and the decision history, dated evidence and case records, which live nowhere
>   else — are in the Chinese text.
>
> The short index is [CONTRIBUTING.md](../CONTRIBUTING.md). Same principle as the CHANGELOG's
> `### Highlights (English)`: **English commits to a summary, not to every line.**

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

**Must go through a PR** (changes that affect runtime behaviour): code in `tools/`,
`web/backend/`, `web/frontend/`, and `tests/`; dependency changes (`requirements*.txt` /
`package.json`); CI / workflow configuration; data-model / schema changes; anything
touching the honesty red lines in [AGENTS.md](../AGENTS.md).

**The PR bar, all required**: the four CI checks green (backend pytest, frontend lint +
build, PR-title check, UI smoke — **red means no merge**) + a self-check against the
[PR template](../.github/PULL_REQUEST_TEMPLATE.md) + **dual-track review**:

1. **Author self-review**: read `gh pr diff` file by file (focus: privacy and the four
   gates, API consumption surface, whether the change is purely additive) and land the
   conclusion as a PR comment;
2. **Independent review**: a **fresh-context** reviewer goes through the same diff as a
   stranger would — a subagent, or `python scripts/review.py` (it auto-detects a second
   CLI, claude / codex: the diff is written to a gitignored file and the reviewer reads
   the files itself, so a large diff is never truncated by an argument size limit; the
   same prompt works across harnesses).

Both rounds — problems found and decisions taken — must stay on the PR page. **Never label
your own review as the independent round, and never fake a review identity.** Issues found
as MAJOR or above in the independent round are fixed on the spot (extra commit) or recorded
for a follow-up PR — never merged silently. Squash and merge; delete the branch afterwards.

> **Exception — bot-authored PRs (decided 2026-09-13)**: dependency-upgrade PRs from the
> official GitHub Dependabot (criteria: the author is `dependabot[bot]` **and** the PR
> carries the `dependencies` label — do not look at the author name alone; it is an
> externally controllable field) **still need the author self-review** and are exempt only
> from the second round. **Patch / minor upgrades only** — a major bump (the dependency's
> own semver first segment changes) does not qualify and goes through a human batch. The
> Chinese title is still required, and the self-review must state "what changed + the
> compatibility judgement". If the bot is swapped or the author does not match, the
> exception does not apply.

**All changes go through a PR** (including text and data-only changes): `main` has branch
protection with `enforce_admins` on, so a direct push is rejected at the protocol level —
and with it, "direct-push text-only changes" from an earlier era is void as a rule.

- **Create the branch before you start** (`git switch -c feat/xxx`); do not write on `main`
  first and check out later — if you forget to branch midway, the commit lands straight on
  `main`.
- **Local commit guardrails (githooks)**: after cloning, run
  `git config core.hooksPath .githooks`. pre-commit: privacy guardrail (`personal/` paths
  and real phone/email patterns are blocked at the commit entrance) + a >1MB file check +
  the size budget (`jobws lint size`, staged files only) + a fast pytest run (degrades to a
  warning when the interpreter lacks pytest; CI is the backstop). commit-msg: Conventional
  format `type(scope): subject` (type restricted to an enum, **the subject must contain
  Chinese**, ≤100 characters), Merge/Revert exempt. The decision logic lives in
  `tools/commit_header.py`, shared with the CI PR-title check. Emergency skip:
  `--no-verify` (explain why in the PR).
- **The PR title is checked too (CI workflow `pr-title`)**: the local hook only runs when
  *you* type `git commit`, whereas the PR title is what GitHub uses to generate the trunk
  commit subject at merge time — **the local hook structurally cannot see it**. On
  violation CI turns red; fix it with
  `gh pr edit <number> --title "feat(scope): 中文说明"`. The workflow explicitly subscribes
  to `edited`, because `pull_request` by default only fires on opened / synchronize /
  reopened — **editing the title does not re-run it by default**.
- **Pre-check the title locally before opening the PR (same implementation; saves a
  round-trip in one second)**: `python tools/jobws.py lint pr-title --title "<the title you
  plan to use>"` — CI is the hard gate, but a local pre-check moves "found out the title is
  invalid only after opening the PR" to before you press Enter.
- **PR granularity is "one independently acceptable batch", not "one commit"**: a branch
  may hold several small commits; open a single PR once everything is done and
  `npm run build` / the tests are green.
- Branch naming (PR path): `feat/<issue-number>-<slug>`, `fix/<issue-number>-<slug>`,
  `docs/<slug>`; lifetime ≤ 1–2 days; delete as soon as it is merged.
- Delete the branch on both sides (`delete_branch_on_merge` handles the remote;
  `git branch -D` locally — **not** `-d`, which necessarily misjudges a squashed branch as
  "not merged"). `python tools/branch_audit.py` only reports; the deletion is a human
  decision.
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
  release" (see §Versioning).
- Breaking changes: the `!` suffix or a `BREAKING CHANGE:` body section; when landed, write
  it into that version's "Breaking changes" subsection in the CHANGELOG (the version number
  itself no longer expresses breakingness).
- **Data operations are committed separately from code**: commits that enter data into the
  workspace use the `data:` / `job:` prefix and are not mixed with feature commits.
- **Language: the commit subject, the PR title and the body are all Chinese.** After a
  squash merge the PR title **becomes the trunk commit subject**, so the two are two halves
  of the same rule — agreeing on commit messages while missing the PR title produces the
  mixed-language result (evidence: the English titles of PR #15 / #16 landed on `main`,
  sandwiched between Chinese commits; full record in the Chinese handbook). Subject and
  title are machine-checked by the hook + CI; **the PR body is not machine-checked** — it
  necessarily contains code blocks, type enums and English terminology, and a machine
  judgement would only produce a noisy gate people bypass; that part is left to the
  dual-track review. The English headers in the issue / PR templates are **fill-in hints**
  for outside reporters, not a language requirement for the body.
  **If you do not write Chinese**: open the PR anyway and say so in the body — your local
  `commit-msg` hook will reject the commit (commit with `--no-verify` and note it) and the CI
  PR-title check will go red; both are harmless, and the maintainer retitles before merging.
- **Merge method**: `main` has `required_linear_history`, so only squash and rebase are
  available. **Use squash** — rebase would lay every original subject from the branch onto
  the trunk verbatim, completely bypassing the PR-title gate.
- **Delete the branch as soon as it is merged (both sides) — do not let them pile up.**
  **Only one criterion is trustworthy for "already merged": the PR record** (`merged: true`)
  — not `git branch --merged main`, and not `git rev-list main..<branch>`: squash rewrites
  commits, so a branch's ancestry never matches `main` again and `git branch -d` refuses,
  making them look "still useful" while they are not. `python tools/branch_audit.py` uses
  exactly that criterion and only reports.
- **Two paths this gate cannot catch (known gaps — do not treat it as omnipotent)**:
    1. **Manually editing the final commit message in the squash dialog**: it changes
       neither the PR title nor triggers `edited`, so nothing re-runs — mechanically
       unstoppable, hence the rule is **do not touch the default commit message when
       merging**.
    2. **A check script that ships in the same PR as the thing it checks**: the workflow and
       `tools/*.py` come from the PR's own branch, so a PR could loosen its own judgement.
       The practical defence is the behaviour pinned in `tests/` — **when you change a
       judgement rule you must change the tests in the same commit and state the reason**.

## Versioning (month-granularity CalVer `YY.MM.N`, since 2026-09-24)

> *Summary tier — the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §版本号体系.*

Semantic versioning is retired (the 0.x mapping and the `v1.0.0` wording are void along with
it). The version is **month-granularity CalVer `YY.MM.N`** (`26.9.0`) — the tag, the
CHANGELOG section name, the `version` in `web/electron/package.json`, `latest.yml`, the
artefact filename and the UI "About" block **are all the same number**. The third segment
`N` = which release of the month (starting at 0); a hotfix moves only the third segment
(`26.9.1` — under electron-updater semantics the only bump that triggers an update; a new
month resets to 0). `web/electron/package.json` is the **single source of truth**; the tag is
`v<version>`, compared **character-for-character** with the version
(`python tools/jobws.py release check --tag v<version>` is the gate). **A single release
point**: intermediate batches do not bump / tag / create a Release / build an installer.
Generate the month's number with `python tools/jobws.py release version`; writing it into
`package.json` is still a manual bump. Other `version` fields (frontend, MCP package) are
private to those packages and must not be tied to the release number.

## CHANGELOG style (single file, two levels, since 2026-09-20)

> *Summary tier — the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §CHANGELOG 写法.*

For an outside release the CHANGELOG is the reader's first stop, so the style is constrained
by "written for humans to read":

- **Two levels per version section**: the section opens with `### Highlights (English)`
  (3–5 lines — **English commits to a summary only, not to every entry**) and
  `### 看得见的变化` (plain-Chinese bullets: verb first, one thing per bullet, PR / issue
  number at the end of the line); raw detailed notes are collected under `### 技术细节`
  below (historical text is not rewritten).
- **Internal engineering entries go to the `Infrastructure` section only** (CI / tests /
  size budget / refactors / packaging / docs proofreading). Criterion = **whether it changes
  the user-visible behaviour of the distributed software**.
- **No naked terminology**: a newly introduced internal term is explained on the spot or
  added to [glossary.md](glossary.md) and linked.
- **Version sections must be self-consistent**: reverse-chronological, compare references
  filled in (pointing at real tags); `[Unreleased]` is the accumulation area and becomes the
  release number + ISO date at release time.

## Release process (manual archiving)

> *Summary tier — the runnable operation sheet is
> [release-checklist.md](release-checklist.md); the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §发布流程.*

Tag from `main`, never release from a branch (**a single release point**). The six steps, in
order:

1. **Manual smoke** (CI has already run the full automated suite; a manual smoke is not
   optional): build the installer → **install and run it once** → open the eight pages with
   real data and operate each one; for UI batches, accept by screenshot comparison.
2. `python tools/jobws.py release version` → write that number into
   `web/electron/package.json`.
3. Turn the CHANGELOG `Unreleased` section into the **version number** + ISO date.
4. **Local pre-check**: `python tools/jobws.py release check --tag v<version>` (tag and
   version character-for-character equal, CHANGELOG section present, release notes preview —
   do not tag while it is red).
5. **dry_run rehearsal**: `gh workflow run release.yml -f dry_run=true -f tag=v<version>` —
   once it passes, `git tag -a v<version> -m "..."` and push.
6. After release, verify with `gh release view --json assets` and **download the artefact
   once for real**.

**Hotfix**: fix-forward — a `fix/` branch through a PR into `main`, released with the third
segment bumped; never branch a hotfix off an old tag. **Withdrawing a bad release**:
re-release with a **higher** number — electron-updater will not accept an identical or lower
one (details in the RUNBOOK in [release-checklist.md](release-checklist.md)). **Auto-update**
is enabled on the Windows packaged build (electron-updater); **macOS auto-update is not done**
(code signing is the remaining blocker).

## Release governance (blocking list / freeze window / tiered verification)

> *Summary tier — the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §发布治理.*

**Release blocking list** — meeting **any** of these means no formal release (treated
separately from ordinary P1/P2; there is no "fix it next batch" option):

1. Data corruption or silent overwriting;
2. Secret / credential leakage;
3. Path-escape class security problems;
4. The installer cannot install or start;
5. A broken update chain (`latest.yml` / auto-update path broken);
6. Main-flow blockage (crashes on open, a core page unusable);
7. Privacy wording inconsistent with real behaviour
   ([data-flow-matrix.md](data-flow-matrix.md) is the authoritative source);
8. Unreliable backup / restore — only a verified restore counts.

Four of them **do not wait for a feature batch** and can go straight to a `26.9.N` hotfix:
**security vulnerabilities / data corruption·silent overwriting / install·startup blockage /
broken update chain**.

**Freeze window (RC stage)**: from the moment a release intent is fixed until the tag,
`main` accepts release-blocking fixes only; everything else queues for the next `N`.
**Tiered verification**: Tier 1 = every PR (full pytest + the seven scanners + frontend
lint / tsc / unit + UI smoke); Tier 2 = after landing on `main` (full E2E suite +
domain-package install smoke + exe smoke); Tier 3 = at release (the full release.yml chain +
install/uninstall smoke + SHA256 + a real-machine manual smoke).

**Outbound-network discipline**: before adding any networking feature, **first** update
[data-flow-matrix.md](data-flow-matrix.md) (and the matching privacy wording in the UI),
**then** change the code — a PR that adds outbound traffic without updating the matrix
should be rejected in review.

## Sustainability commitments

- **Make the time box public**: the README states the **shape of the investment** (in
  batches — a few days of focused work, or a whole week with nothing; outage windows below)
  and the **response target** (first reply to an issue within 48 hours, slips disclosed, see
  [maintenance.md](maintenance.md)); **no throughput numbers** — the number of PRs
  fluctuates with tooling and batches and is not a stable promise.
- **Outage windows**: no development during interview weeks / written-exam weeks — the
  project serves the job hunt, it is not the opposite of it.
- **Issue cap**: once unhandled issues exceed 30, triage and close to prevent a backlog
  paralysis.
- **Vision first**: major directions get a design note first (`docs/specs/`), so that people
  can leave and the vision keeps the project moving.

## For AI collaborators

> *Summary tier — the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §AI 协作者. Measured numbers (case counts,
> timings, dependency upper bounds) live there only and are deliberately not duplicated here:
> they move with the batches, and a stale copy is worse than none.*

- This document and [AGENTS.md](../AGENTS.md) are complementary: this one governs
  "process", AGENTS.md governs "data layering and honesty red lines" — they do not repeat
  each other.
- AI changes are subject to the four gates just the same; when a requirement cannot reach
  the third gate, suggest downgrading it to a throwaway script or `personal/`
  configuration.
- **Run the verification before committing; never write "it should run" into a commit
  message.**
- **Local verification chain (the same as CI)**: `pip install -r
  web/backend/requirements-dev.txt` → `python -m pytest tests/ -q` (check that the case
  count was not accidentally under-collected) → `python tools/jobws.py lint
  {i18n,ui-tokens,themes,four-ends,size}` (**one check name per invocation** — expand the
  braces) → frontend `npm run lint` + `npm run build` (`npm.cmd` on
  Windows) → **if you changed pure logic** add cases to `web/frontend/tests/unit/`
  (`npm run test:unit`, Vitest) → **for UI changes also run `npm run test:ui`** (needs
  `npm run build` first and a demo workspace: `python tools/jobws.py init --target demo
  --demo`).
- **Interpreter baseline: 3.12** (the only supported and verified version; the technical
  floor is ≥3.9, but anything lower is **silently untrustworthy** — `tests/conftest.py`
  stops it before collection). The pre-commit hook and `web/start.ps1` resolve in the order
  `JOBWS_PYTHON` > the repository's `.venv` > the interpreter running them, so they do not
  depend on which environment the terminal has activated; below 3.12 the hook **degrades to
  a warning instead of blocking** (CI is the backstop).
- **Install the domain package before developing**: `pip install packages/jobws-core`
  (packaging and CI use a non-editable install; for local development
  `uv pip install -e packages/jobws-core --config-settings editable_mode=compat` puts the
  whole `src` on the path so new modules become visible without reinstalling).
- **`jobws lint legacy-imports`**: legacy-name import sites are a **monotonically
  decreasing** budget (`tools/legacy_imports_allowlist.txt`); new code always uses
  `jobws_core`, and cleared names stay in `LEGACY_NAMES` as a firewall.
- **After changing dependencies you must run `npm run lint` / `tsc` / `vite build`**:
  `npm install` exiting 0 **does not mean it is usable**.

## Developer tooling (MCP / code graph — for developers and AI, not the product)

> *Summary tier — the authoritative full text is
> [contributing.zh-CN.md](contributing.zh-CN.md) §开发者工具.*

The project distinguishes **product runtime dependencies** (what an end user needs to run
it: a browser + Chrome + the `tools/` scripts + the web layer) from **development aids**
(GitNexus impact analysis, CodeGraph code graphs, Playwright for clicking through pages).
The former live in the repository and ship with the project; the latter belong to the
**developer's personal environment** — hence "CONTRIBUTING mentions GitNexus/Playwright" and
"the product does not include them" are not in conflict.

The code-graph index is a **per-repository runtime artefact** already excluded by
`.gitignore` (`.gitnexus/`, `.codegraph/`); after a clone / machine change, rebuild it once
with `powershell -ExecutionPolicy Bypass -File scripts/index_dev_tools.ps1` (assumes
`gitnexus` and `@colbymchenry/codegraph` are installed globally; an MCP declaration sample
is in `.codebuddy/mcp.example.json`).

**Privacy reminder**: those index caches record file names / symbols locally — they are
gitignored and never enter the repository, but **do not send them anywhere either**.

Note: on product PRs there is **no full** Playwright E2E (only the minimal UI smoke, pinning
layout and serious/critical a11y; the full suite runs in the `e2e-full` job after a push to
`main`); **manually clicking through a page with Playwright while developing** is not
covered by that rule and is not restricted.

## Four-end consistency (must be synced when adding a capability)

The same capability working in **four entrances — command line / AI host (MCP) / editor
plugin / desktop UI** — is a design premise; the contract source of truth is
`tools/four_ends_matrix.json`, and the human-readable comparison page
[four-ends.md](four-ends.md) is generated from it.

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
- Distributing assets to the harnesses: `python tools/jobws.py skills install` — since batch
  10 it distributes **three kinds of assets** at once (skills / commands / subagents;
  landing points documented in the script header). **Zero-clone channels** (plugin
  marketplace install, `npx skills add`) are in the README "Quick start"; the
  in-repository project-level copies are compared item by item by the checker above
  (user-level `~/.agents/skills/` and plugin-market caches are out of its sight — they do
  not travel with the repository, see
  [support-and-compatibility.md](support-and-compatibility.md)).

## Copy & i18n (UI strings always go through `t()`)

- **All UI copy goes through `t()`**: add keys to
  `web/frontend/src/i18n/locales/zh-CN.ts` (the source language, the single source of truth
  for keys); `en.ts` uses `satisfies Record<TranslationKey, string>` to pin the two key sets
  together **at compile time** — one extra, one missing, or one typo fails the build.
- **Four things are not translated**: code comments (Chinese comments are this project's
  documentation convention); domain data (stage / batch / round / direction / terminal-state
  enums, CSV column names, Chinese field names in the API — translating them would
  desynchronise the UI from your history and the CLI); the user's own content; real file and
  directory names in the workspace.
- **One convention for loanwords in the Chinese UI**: Chinese first, with the original in
  full-width parentheses — `服务地址（Base URL）`, `API 密钥（API Key）`,
  `模型服务（Provider）`; protocol and format abbreviations (IMAP / CSV / JSON / PDF / JD /
  URL) keep their original form. **The same word is written the same way across the
  codebase**; error strings, buttons and hints change together, not one at a time.
- **Container components take their copy from the caller**: hard-coding a default Chinese
  sentence inside a component counts as hard-coding too (`emptyLabel ?? t("…")` is the
  correct form).
- **Module-level constant tables cannot call `t()`**: store `labelKey: TranslationKey`
  instead (`import type { TranslationKey }`) — the type annotation is the compile-time
  guardrail, and the rendering site calls `t()`.
- **The backend does not guess the language**: throw
  `ApiError(status, code, detail, **params)` (`web/backend/apierror.py`); `detail` keeps the
  original Chinese (debugging and issues read it), and the UI copy is looked up by the
  frontend from the `err.<code>` catalog, falling back to `detail`. Code naming is
  `<domain>.<semantics>` and **the same semantics reuse the same code**; user-visible
  dynamic values go through `params`, never hard-coded in the copy. **Unexpected exceptions
  have a backstop too**: the global handler in `main.py` turns any uncaught exception into
  `server.error` + a readable detail (full traceback to the log) — a bare
  `Internal Server Error` never reaches the UI.
- **Automated check**: `python tools/jobws.py lint i18n` (runs in CI, always available
  locally; it blocks on a hit). It checks four classes whose common trait is that **the UI
  would show a raw key name or a word in the wrong language, and neither tsc nor lint can
  see it**: ① hard-coded Chinese; ② a plural key missing its `count`; ③ a `t()` key that
  does not exist; ④ **hard-coded English** (bare JSX text outside `t()`,
  `title`/`aria-label`/`alt`/`placeholder` literals, and the Electron window/dialog copy —
  scope defined by `EN_SCOPE_RELS`: `web/frontend/src/pages/**`,
  `web/frontend/src/components/**`, `web/electron/**`). The narrow scope is deliberate (false
  positives make people stuff the allowlist, and the check then dies); **before widening
  the scope, do a dry run with `--list` and classify the false positives**. Its deliberately
  uncovered forms and known boundaries are written in the implementation comment — do not
  read "the check passes" as "no English remains".
- **Allowing data-shaped hits**: register them in `tools/i18n_hardcode_allowlist.txt`:
  `path = fragment1|fragment2  # reason`; **English hits go in the `en:` section**
  (`en:path = fragment  # reason`) — the two allowlists are not interchangeable, and the
  prefix **must be lowercase**. **Only the listed fragments are allowed, never a whole
  file** (a whole-file exemption once let 4 untranslated strings pass green). The list is a
  "snapshot of the present": when the sentence gets translated or the file is deleted, the
  entry must be deleted too. To regenerate a draft:
  `python tools/jobws.py lint i18n --print-allowlist`; the reasons are written by a human.
- **Verification**: after changing the frontend run `npx tsc -b` + `npx eslint .`; leave
  `npm run build` to CI (a local vite run rewrites hundreds of files in `dist/`).

## Code hygiene (borrowed from an anti-shit-mountain checklist, trimmed to six clauses)

Self-check while writing; re-check during PR self-review:

1. **Size budget** (measured automatically by `jobws lint size`; the backlog is registered
   in `tools/size_allowlist.txt`):
   - **Logic type** (business code): a file ≤300 lines; a single function ≤60 lines,
     **> 80 must be split** into "an orchestrator + ≥2 helpers"; nesting ≤3 levels.
   - **Data/declaration type** (i18n catalogs, constant tables, tests and fixtures): ≤1500
     lines — that kind of code has many lines and low complexity. The classification is in
     `classify()` in `tools/check_size.py`.
   - **Backlog exempt, increments gated**: files already over the limit are registered in
     `tools/size_allowlist.txt` (`path = lines  # reason`), and **the registered value is
     the water line** — it may only go down, never up; when it drops within the threshold
     the checker demands deleting the entry (self-cleaning). **New files are never allowed
     to exceed it.**
2. **Extraction timing (rule of three)**: consider extracting the second time the same
   logic appears; the third time it must be extracted into a shared module; when a third
   `if/elif` branch appears with each branch >10 lines, extract a dispatch.
3. **No silent error swallowing**: `except Exception: pass` and empty `catch {}` are
   forbidden — at least log (`logger.warning` / `console.error`).
4. **Single source of truth**: the same enum/mapping/constant is defined in exactly one
   module and referenced elsewhere — a second inline copy is collapsed back to the
   registry.
5. **All runtime product code must be covered by at least one structural check**:
   `.py / .ts / .tsx / .js / .mjs` × `tools/`, `packages/`, `web/backend/`,
   `web/frontend/`, `web/electron/`, `mcp/`, `scripts/`. **When adding a runtime code
   directory or suffix you must sync `SCAN_DIRS` / `SOURCE_SUFFIX` in
   `tools/check_size.py`.**
6. **Two channels for failure paths**: problems such as a failed start, a backend crash, a
   failed update or a failed restore must have **both** a user-visible message and a local
   structured log; the diagnostics bundle fields are fixed (version / platform / log tail)
   and **always exclude** résumés, mail, API keys, passwords and workspace content
   (`web/electron/diagnostics.js` plus tests pin this down).

## Explicitly not doing (over-engineering)

`develop`/`release`/`hotfix` branches, semantic-release, a GitHub Projects board,
requirement voting tools, a complex label system, a standalone roadmap site, **a full**
Playwright E2E suite on PRs (the PR gate only pins "the page opens / no horizontal overflow
/ the top bar does not wrap / no console errors / zero serious+critical a11y issues", while
the full suite runs in the `e2e-full` job after a push to `main` — rationale: this class of
layout breakage has happened twice in practice, and tsc, eslint and the judgement scripts
cannot see it), code signing.

(Basis: `docs/research/report_dev_workflow.md` — the minimum-viable trade-offs of a
single-maintainer project. Exceptions: minimum CI, minimum UI smoke, and **branch
protection** — linear history + force-push disabled, including for admins. GitHub branch
protection cannot distinguish "code vs docs" by path, so the tiering is upheld by the rules
in §Branching strategy, with `revert` as the fallback when something slips.)
