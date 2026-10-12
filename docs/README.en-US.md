# Doc index

Listed in reading order. If you are not sure where to start, start from the first one.

This is the English companion of the index; the 简体中文版 with the same structure is [`README.md`](README.md).

## Start here

| Document | What it is |
|---|---|
| [`usage-guide.md`](usage-guide.md) | **Usage guide (English main)**: environment setup, one-command start, the eight pages, AI workflows, CLI reference, backup, FAQ |
| [`usage-guide.zh-CN.md`](usage-guide.zh-CN.md) | 简体中文同步版 of the guide above (same content, cross-linked at the top of each side) |
| [`README.md`](README.md) | This index, 简体中文版 |
| [`../README.md`](../README.md) | Project entry point: positioning, three-layer architecture, quick start, directory map |
| [`data-flow-matrix.md`](data-flow-matrix.md) | **Data-flow matrix**: what data goes where, and when — the authoritative source for the privacy promise (when UI copy conflicts with it, the matrix wins) |

## Design documents

| Document | Status | What it is |
|---|---|---|
| [`specs/2026-10-04-single-canonical-data-root.md`](specs/2026-10-04-single-canonical-data-root.md) | **Current** | Single canonical data root & legacy-workspace migration: four surfaces converge on one resolver, tri-state guards (ambiguous / unavailable / uninitialized), persisted root choice, migration transaction (copy → verify → switch, resumable and revertible) and the cross-surface contract matrix |
| [`specs/2026-08-30-general-workbench-design.md`](specs/2026-08-30-general-workbench-design.md) | **Current** | v2.0 general-workbench architecture: three-layer separation, domain-profile contract, parameterized scripts, migration map. **Note**: inventories such as "6 scripts under tools/" are records from Aug 2026 — the scripts have since merged into the single `tools/jobws.py` entry; for the current state see `contributing.zh-CN.md` |
| [`specs/2026-08-30-web-prototype-design.md`](specs/2026-08-30-web-prototype-design.md) | Historical (some sections superseded) | Web UI layer: architecture, API contract, data contract, concurrency & security, verification records. **Note**: dependency versions and the Python baseline are records from Aug 2026 (the 3.8 era); for the current state see `contributing.zh-CN.md` and `web/backend/requirements.txt` |
| [`specs/2026-08-31-job-workbench-productization.md`](specs/2026-08-31-job-workbench-productization.md) | **Current** | Productization in three phases (differentiation / architecture / desktop shell / extensions) + phase-1 and P0+P1 completion records |
| [`specs/2026-09-02-tracking-enhancement.md`](specs/2026-09-02-tracking-enhancement.md) | **Current** | Application-tracking enhancement: separate CSVs for interviews / contacts / offers, anti-fabrication guardrails, timeline |
| [`specs/2026-09-02-resume-data-driven.md`](specs/2026-09-02-resume-data-driven.md) | **Current** | Data-driven resume "standard layout": JSON + built-in template → PDF + ATS validation. **Note**: old commands like `resume_build.py render` now only print a migration hint and exit 2 (current: `python tools/jobws.py resume …`); "Python 3.8 compatibility" was the baseline back then (now 3.12) |
| [`specs/2026-09-02-resume-probe.md`](specs/2026-09-02-resume-probe.md) | Done | Resume-PDF text-extraction probe (the basis for the ATS thresholds) |
| [`specs/2026-09-03-p0-p3-roadmap.md`](specs/2026-09-03-p0-p3-roadmap.md) | **Current** | P0–P3 four batches: engineering base, post-application loop, enhancements, long-term assets (with acceptance records) |
| [`specs/2026-09-05-batch1-3-roadmap.md`](specs/2026-09-05-batch1-3-roadmap.md) | **Current** | Batches 1–3: import/export loop, question bank & health, failure clustering and JD fetching (with acceptance records) |
| [`specs/2026-09-07-open-source-release.md`](specs/2026-09-07-open-source-release.md) | **Current** | Open-source release: privacy cleanup, MIT, governance entry, CI and release flow. **Note**: the opening "current-state audit" (missing LICENSE, `.github/` holding only ISSUE_TEMPLATE…) is a record from 2026-09-07 and has since been reversed; the repo itself is authoritative |
| [`specs/2026-09-28-project-site-design.md`](specs/2026-09-28-project-site-design.md) | **Current** | Project site design: a docs site reachable from mainland China (MkDocs Material) — single-source content (whitelist assembly from `docs/`), download design (GitHub Releases + SHA256 checksums), zero-cost and privacy boundaries |
| [`specs/2026-09-28-project-site-plan.md`](specs/2026-09-28-project-site-plan.md) | **Current** | Implementation plan for the design above: assembler / skeleton / CI / homepage / download page / repo registration / launch verification — seven tasks with per-step verification and review focus |
| [`specs/2026-08-30-autumn-recruit-workbench-design.md`](specs/2026-08-30-autumn-recruit-workbench-design.md) | ⚠️ **Deprecated** | v1.0 personal-tool design. The directory structure is obsolete — **do not build against it**. Kept as the design-trail reference for the scoring framework |
| [`domain-contract.md`](domain-contract.md) | **Current** | Domain-profile contract: structure, formats, boundaries and how it is validated (the basis for `jobws lint domains`) |

## Research reports

| File | What it is |
|---|---|
| [`research/report_job_search_products.md`](research/report_job_search_products.md) | Survey of open-source job-search products on GitHub (**product-feature layer**): competitor landscape, LLM-integration consensus, differentiation opportunities (traceable scoring / eligibility gate first), productization takeaways |
| [`research/plan_job_search_products.md`](research/plan_job_search_products.md) | Research plan for the survey above (search terms, subagent split, parallelism) |
| [`research/report_dev_setup_benchmark.md`](research/report_dev_setup_benchmark.md) | Local-first desktop-app dev-setup benchmark (**engineering-config layer**): packaging & distribution (PyInstaller onedir/onefile), user-data directory strategy, engineering setup (CI / lockfiles / logging) — highlights and gaps |
| [`research/plan_dev_setup_benchmark.md`](research/plan_dev_setup_benchmark.md) | Research plan for the benchmark above (three-way split on the engineering-config layer) |
| [`research/report_dev_workflow.md`](research/report_dev_workflow.md) | **Development workflow** of similar projects (iteration rhythm, branching & release, requirement management, **self-use vs productization balance**) and actionable process suggestions for this project |
| [`research/plan_dev_workflow.md`](research/plan_dev_workflow.md) | Research plan for the workflow survey (three-way split on the workflow layer) |
| [`research/report_next_features.md`](research/report_next_features.md) | **Feature-level gap analysis** for the next step: feature lists from four search domains (one interrupted) and borrow-priority notes (different split from the product-positioning survey above — that one answers "what to become", this one "what is missing"). Note: the fourth search path was interrupted; the conclusions do not depend on it, and the missing part is listed at the top |
| [`research/plan_next_features.md`](research/plan_next_features.md) | Research plan for the gap analysis (four non-overlapping feature domains) |
| [`research/report_agent-integration.md`](research/report_agent-integration.md) | **Positioning & host-integration** consolidation (decision level): costs and counter-evidence for the agent-plugin/tool path, a dsh plugin dissection, agent-first layering, exposing Python tools to agents. **This is the basis for "the AI assistant is a first-class host, the UI is an optional viewer"**. It is a conclusion consolidation (subagent reports were truncated by the scheduler); unconfirmed parts are listed at the end — do not treat it as a full survey |
| [`research/report_electron_33_to_44.md`](research/report_electron_33_to_44.md) | **Electron 33 → 44 upgrade survey** (execution level): official breaking changes checked line-by-line against our actual API surface (with `main.js` line references) → risk tiers + desktop smoke checklist. Conclusion: CI never touches Electron, so "CI green" is not evidence for the upgrade; what actually needs verification is the packaging chain (v42+ no longer downloads binaries in postinstall), the zoom four-piece, auto-update and PDF preview |
| [`research/report_full_repo_audit_2026-09-16.md`](research/report_full_repo_audit_2026-09-16.md) | **Full-repo audit (2026-09-16)**: structure / dependencies / config / size inventory, findings and prioritized improvements — the basis for the governance and remediation batches (docstrings and numbers are snapshots of that time) |
| [`research/oauth2-imap-feasibility.md`](research/oauth2-imap-feasibility.md) | **Outlook / enterprise-mail OAuth2-for-IMAP feasibility** (2026-09-24): Google / Microsoft app registration and local-callback requirements, token-storage trade-offs, zero-dependency effort estimate and recommendation — conclusion: "not in v1; trigger conditions inside", every point sourced, unverified items flagged |

## Development process

| File | What it is |
|---|---|
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | **Contributing entry (short English index, matching the English-first README)**: privacy red lines, environment setup, local verification chain, commit & PR rules, four gates for new requirements — pointing to the full Chinese rules and the English reading companion below |
| [`contributing.zh-CN.md`](contributing.zh-CN.md) | **The full Chinese rules (authoritative)**: branching & dual-track review, commit conventions, version scheme, changelog style, release process & governance, sustainability, i18n conventions, code hygiene |
| [`contributing.en-US.md`](contributing.en-US.md) | **English reading companion (two-tier promise)**: the contributor-required sections (positioning, privacy, four gates, branching & PRs, commits, four-ends consistency, i18n, code hygiene, non-goals, sustainability) are in sync with the Chinese version; the governance sections (version scheme, changelog style, release process & governance, AI collaborators, dev tooling) are summaries only — the full text and the decision history live in the Chinese version, which wins on any conflict |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Change log (single file, two levels: plain-language 「看得见的变化」 + English Highlights + 「技术细节」; format based on Keep a Changelog); the single source of the version number is `web/electron/package.json` |
| [`four-ends.md`](four-ends.md) | Four-surface capability comparison and exception list (the explainer for `jobws lint four-ends`, generated from `tools/four_ends_matrix.json` — do not hand-edit) |
| [`glossary.md`](glossary.md) | Glossary (简体中文版): the internal terms of these docs and the changelog, defined once |
| [`glossary.en-US.md`](glossary.en-US.md) | Glossary (English companion of the table above; terms stay Chinese, meanings in English) |
| [`maintenance.md`](maintenance.md) | Repo maintenance notes (English): release rhythm, version-number discipline, and the outward-facing statement of project health |
| [`support-and-compatibility.md`](support-and-compatibility.md) | **Graduation criteria, support policy and data-compatibility promise**: when this counts as a stable release (four criteria), which environments are supported, and why upgrades never require converting your data |
| [`release-checklist.md`](release-checklist.md) | **Release checklist**: CI-automated items (three gates / install-uninstall smoke / SHA256 / SmartScreen notice) and manual must-dos (real-machine notification test / human acceptance / version bump & dry run), plus the 72-hour post-release and rollback RUNBOOK |
| [`releases/`](releases/) | **Release verification records (one per version, never rewritten)**: `26.9.0-verification.md` / [`26.10.0-verification.md`](releases/26.10.0-verification.md) — tag, commit, workflow run, asset hashes, real-machine items and post-release checks (`release-checklist.md` is the operating sheet, reset for the next version) |
| [`../SECURITY.md`](../SECURITY.md) | Security policy: threat model, local-first trade-offs (e.g. the unsigned auto-update chain) and how to report |
| [`../ROADMAP.md`](../ROADMAP.md) | Roadmap: Now / Later plus a shipped-batch log (details in the changelog) |
| [`../THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md) | Third-party dependencies and licenses |
| [`../.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) | Issue templates: bug report and feature request (the latter includes a fit check; new requirements still run the four gates in CONTRIBUTING) |

## Decision records (ADRs)

One decision per file, filename = imperative verb + kebab-case. "Why it is this way" lives here; the roadmap and changelog only record "what was done".

| File | What it is |
|---|---|
| [`decisions/keep-hooks-local-and-off.md`](decisions/keep-hooks-local-and-off.md) | Host hooks stay local and off by default; not implemented in this batch (with alternatives and review triggers) |
| [`decisions/keep-writes-human-confirmed.md`](decisions/keep-writes-human-confirmed.md) | Writes are always human-confirmed: no auto-applying, no logging in for you, AI output never lands directly on disk |
| [`decisions/ship-once-per-release.md`](decisions/ship-once-per-release.md) | Single release node + month-granularity CalVer (`YY.MM.N`; changed from a four-segment timestamp scheme on 2026-09-24, original text kept with an update note) |
| [`decisions/read-missing-columns-as-empty.md`](decisions/read-missing-columns-as-empty.md) | Workspace data stays backward-compatible: missing columns read as empty, headers written uniformly, no user-side migration |
| [`decisions/code-signing.md`](decisions/code-signing.md) | Code signing: not purchased for now (option matrix / trigger conditions / remediation checklist if triggered; 2026-10-02) |
| [`decisions/single-canonical-data-root.md`](decisions/single-canonical-data-root.md) | Single canonical data root & legacy-workspace migration: one resolver across four surfaces, persisted choice, fail-closed staleness, migration transaction; route A→B→C′ (2026-10-04, with alternatives and review triggers) |
| [`decisions/first-class-delivery-surfaces.md`](decisions/first-class-delivery-surfaces.md) | First-class delivery surfaces and integration boundaries: peers across surfaces (capability equivalence, not implementation equivalence), a single release line, runtime-independent / domain-shared, dependency direction, repo-split review signals (2026-10-06) |
| [`decisions/port-identity.md`](decisions/port-identity.md) | Port identity: what decides who owns 8765 (structured health response), the "reuse if already running" boundary, and "kill processes only from dev scripts" (2026-10-07) |

## Convention files

| File | What it is |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | AI working conventions: three-layer architecture rules, general/personal boundary, engineering constraints, directory conventions |
| [`../template/AGENTS.example.md`](../template/AGENTS.example.md) | Candidate-profile template (简体中文版), with per-item notes and a real example |
| [`../template/AGENTS.example.en-US.md`](../template/AGENTS.example.en-US.md) | English companion of the profile template — use its content for your workspace `AGENTS.md` |
| [`../template/workspace/README.md`](../template/workspace/README.md) | The six modules: purpose, filling order, key discipline (简体中文版) |
| [`../template/workspace/README.en-US.md`](../template/workspace/README.en-US.md) | English companion of the workspace-skeleton guide |

## Domain profiles

**Which `--domain` to pick** — find your field below (details in each profile's `profile.md`):

| Plugin ID | Who it is for | Covered roles |
|---|---|---|
| `hvac-cooling` | HVAC, building environment, energy & power, refrigeration and related majors | Data-center cooling / thermal management, IDC infrastructure, air-conditioning & refrigeration R&D, HVAC design, building energy efficiency, liquid cooling products, energy-storage thermal management |
| `software-backend` | Computer science, software engineering, data science and related majors | Backend development, server-side development, data engineering, big-data development, platform engineering |

| File | What it is |
|---|---|
| [`../template/profiles/hvac-cooling/profile.md`](../template/profiles/hvac-cooling/profile.md) | HVAC-cooling & data-center-cooling profile (built-in directions: `datacenter`, `hvac`, `thermal-management`, `thermal-fluid-cfd`, `thermal-design-cae`, `energy-storage-thermal`) |
| [`../template/profiles/software-backend/profile.md`](../template/profiles/software-backend/profile.md) | Software-backend & data-engineering profile (built-in directions: `backend`, `data`; also the reference example for cross-domain extensibility) |

Adding a field means adding one profile directory, no code changes — **the full contract is in [`domain-contract.md`](domain-contract.md)** (structure, formats, boundaries, validation); run `python tools/jobws.py lint domains` before submitting (same implementation as CI).

## Skill files (workflow definitions)

Nine under `../skills/`: five job-hunting — `jwb-recruit-coach` (scoring standard & red lines), `jwb-jd`, `jwb-apply`, `jwb-track`, `jwb-resume`; one extensibility — `jwb-domain-setup` (generate / customize a domain profile, human-confirmed); three development — `jwb-cli-contract` (CLI contract), `jwb-api-review` (API review), `jwb-mcp-server` (MCP guide).

These are both skills the AI can load and the specification of each workflow — reading them is reading the process definition.

## Component READMEs

| File | What it is |
|---|---|
| [`../web/README.md`](../web/README.md) | Web UI layer: the eight pages, its relationship to the CLI, directory structure, known boundaries |
| [`../web/frontend/README.md`](../web/frontend/README.md) | Frontend engineering notes (build chain and how to run it) |
| [`../mcp/README.md`](../mcp/README.md) | MCP service: 16 tools (8 read-only + 7 two-phase previews + `apply_approval`; read-only includes the data-root diagnostic `jobws.info` and the job-text reader `read_job_text`), installation & host configuration, workspace resolution |
| [`mcp-integration.md`](mcp-integration.md) | MCP integration deep-dive: installation, host configuration (four forms, different key names), workspace resolution, two-phase usage and troubleshooting |

## Archived code

| File | What it is |
|---|---|
| [`deprecated/fix_links.py`](deprecated/fix_links.py) | A one-off broken-link fixer used during a personal reorganization; retired. Kept as a reference for path-rewrite logic |
