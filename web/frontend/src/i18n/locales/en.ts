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
} satisfies Record<TranslationKey, string>;
