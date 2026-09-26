// 提醒条的展示判定（纯函数，零依赖）。
//
// 与 lib/snapshotMeta.ts 同一条理由：把"该显示什么"从组件里抽出来，单测直接钉住三态。
// 注意本模块**不能** import http / i18n 这类浏览器依赖——vitest 刻意不引 jsdom
// （见 web/frontend/tests/unit/ 的既有约定），拉了就会 "document is not defined"。
import type { RemindersDue } from "./domainTypes";

/** 提醒条的一行（文案键与跳转目标；渲染在 components/ReminderBar.tsx）。 */
export interface ReminderLine {
  kind: "overdue" | "todos" | "talks";
  count: number;
  /** hash 路由目标（App 的 hashchange 监听会切 tab） */
  href: "#applications" | "#prepare";
  /**
   * i18n **基础键**（调用时带 count 走 _one / _other）。
   *
   * 收成字面量联合而不是 string：`t()` 的静态检查只认字面量，变量键会从
   * i18n 扫描器（`jobws lint i18n` 的"key 必须存在"一档）与 `TranslationKey`
   * 编译期检查**双双漏过**——收窄到这三个名字，至少让改名时 TS 先报错。
   */
  labelKey: "reminder.overdue" | "reminder.upcoming" | "reminder.talks";
  /** 逾期 = 警报（整条转 destructive 色）；待办 / 宣讲会 = 提醒 */
  severity: "alert" | "warn";
}

/**
 * 提醒条要显示哪几行：计数为 0 的来源不出现；全为 0（或后端未答）时返回空数组
 * ——整条不渲染，不留空壳。
 *
 * 顺序固定为 逾期 → 待办 → 宣讲会（最急的在前）。
 *
 * 对畸形答复设防：后端返回 200 但缺 `counts`（旧壳 / 代理 / 半截响应）时返回空数组，
 * **不抛错**——否则会被全站 ErrorBoundary 接住，把"少一条提醒"升级成"整站渲染失败"。
 */
export function reminderLines(due: RemindersDue | null): ReminderLine[] {
  const counts = due?.counts;
  if (!counts) return [];
  const lines: ReminderLine[] = [];
  if (counts.overdue > 0) {
    lines.push({
      kind: "overdue", count: counts.overdue, href: "#applications",
      labelKey: "reminder.overdue", severity: "alert",
    });
  }
  if (counts.todos > 0) {
    lines.push({
      kind: "todos", count: counts.todos, href: "#applications",
      labelKey: "reminder.upcoming", severity: "warn",
    });
  }
  if (counts.talks > 0) {
    lines.push({
      kind: "talks", count: counts.talks, href: "#prepare",
      labelKey: "reminder.talks", severity: "warn",
    });
  }
  return lines;
}
