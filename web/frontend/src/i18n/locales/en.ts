import type { TranslationKey } from "./zh-CN";

/** 英文文案。key 必须与 zh-CN 完全一致——satisfies 在编译期钉住：
    少一个 key、多一个 key、拼错一个 key，tsc 直接报错（不靠人盯）。 */
export default {
  "app.title": "Job Workbench",

  "nav.dashboard": "Dashboard",
  "nav.applications": "Tracker",
  "nav.jobs": "Job Pool",
  "nav.resume": "Resume Workshop",
  "nav.progress": "Progress",
  "nav.library": "Library",
  "nav.settings": "Settings",

  "nav.workspacePlaceholder": "Select workspace",
  "nav.workspaceDefaultSuffix": " (default)",
  "nav.switchWorkspaceTitle": "Switch workspace",

  "status.connecting": "Connecting",
  "status.online": "Local data connected",
  "status.offline": "Backend not running",
  "error.backend": "Cannot connect to the backend (localhost:8765)",
  "error.backendHint": "Run from the repository root:",
  "error.renderFailed": "Something went wrong rendering this page",
  "error.forceReload": "Hard reload (clear cache)",

  "common.retry": "Retry",
  "common.close": "Dismiss message",
  "loading.workspace": "Locating workspace…",

  "lang.switch": "Language",

  "job.unscored": "Unscored",
  "job.notScored": "Not scored yet",
  "job.jdSaved": "JD saved",
  "job.reapplyHint": "Applying again creates a new record",
  "job.applyHint": "After applying, follow up in the tracker",
  "job.applying": "Applying…",
  "job.reapply": "Apply again",
  "job.apply": "Apply now",
  "job.cardAria": "{{dir}}, match {{score}}, application status {{state}}",

  "lineage.title": "Version lineage",
  "lineage.subtitle": "Which jobs each version went to, and how far they got",
  "lineage.loadFailed": "Failed to load version lineage: {{error}}",
  "lineage.jobCount_one": "{{count}} job",
  "lineage.jobCount_other": "{{count}} jobs",
  "lineage.tip": "Tip: fill in the 简历版本 (resume version) column in the tracker when you apply — that is what links a version to its jobs.",

  "job.backToPool": "Back to job pool",
  "job.hardGates": "Eligibility gates",
  "job.gatePending": "Pending",
  "job.gateReason": "Reason: {{reason}}",
  "job.jdSource": "JD source",
  "job.jdMissing": "(JD not saved yet)",
  "job.parsedCard": "Parsed card",
  "job.nextStep": "Next step: {{action}}",
  "job.cardMissing": "No parsed card yet",
  "job.cardEmptyHint1": "Scoring is done by the AI in CodeBuddy (the jd workflow); once it is written to",
  "job.cardEmptyHint2": "the four dimension scores and the tier show up here automatically.",
} satisfies Record<TranslationKey, string>;
