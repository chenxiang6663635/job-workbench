// 到点提醒的读取封装：**刻意不进 src/api.ts** —— 那个文件登记过水位（460 行，
// 只许变小），窄需求走窄模块（与 lib/bank.ts、lib/snapshotApi.ts 同一条理由）。
//
// 类型在 lib/domainTypes.ts 统一声明（中文字段名是数据契约，与 web/electron/reminders.js
// 同源；按仓库惯例类型不散落在窄模块里）。展示判定在 lib/reminderMeta.ts（纯函数，
// 零依赖——本模块拉进了 http/i18n，不能进 vitest 的 unit 测试）。
//
// 与主进程的职责分工：系统通知负责"你没看 app 时戳你一次"（每天一次，走 Electron
// Notification）；这里负责"你已经打开了 app，把今天的事摆在最上面"（ReminderBar）。
// 两处读的是同一个端点，判据在 web/backend/remind.py 收口。
import type { RemindersDue } from "./domainTypes";
import { requestJson } from "./http";

/**
 * 今天到点的事：提前 window 天内的待办 / 近 7 天宣讲会 / 已过期。只读。
 *
 * `days` 是「提前几天」（3/5/7，真值在主进程偏好里，由调用方读出后传入）：
 * 不传则用后端默认 3——**不要在这里再定一个默认值**，两处默认值迟早会漂移。
 */
export function fetchReminders(days?: number): Promise<RemindersDue> {
  const query = typeof days === "number" && Number.isFinite(days) ? `?days=${days}` : "";
  return requestJson<RemindersDue>(`/reminders/due${query}`);
}
