/**
 * 本地日期口径的唯一实现。
 *
 * 此前这段 logic 抄在三处（`Jobs` 的 `today()`、`Dashboard` 的 `shiftDate()`、
 * `ContactList` 的 `toISOString()`），一处本地、一处 UTC 就会漂：`toISOString()`
 * 取的是 UTC 日期，UTC+8 的 0–8 点会给出"昨天"（写进追踪表的日期直接错一天）；
 * 而 `new Date("2026-09-30")` 按 UTC 零点解析，比本地同一天早 8 小时，让
 * 「3 天内到期的 offer」在临界点上判错。写回与比较都只看日历日，所以这里一律按
 * 本地时区构造 Date，格式也统一为 `YYYY-MM-DD`。
 */

/** 今天（`YYYY-MM-DD`，本地时区）：表单默认值与「标记今天已联系」这类写回用它。 */
export function todayISO(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * 按**本地**时区解析 `YYYY-MM-DD` 或 `YYYY-MM-DD HH:mm`（秒与时区后缀忽略）。
 * 解析不出来返回 null——调用方据此决定忽略，而不是拿一个 Invalid Date 去比较。
 */
export function parseLocalDate(value: string): Date | null {
  const text = (value || "").trim();
  if (!text) return null;
  const hit =
    /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(text);
  if (!hit) return null;
  const [, y, m, d, hh, mm, ss] = hit;
  const date = new Date(
    Number(y),
    Number(m) - 1,
    Number(d),
    hh ? Number(hh) : 0,
    mm ? Number(mm) : 0,
    ss ? Number(ss) : 0,
    0,
  );
  return Number.isNaN(date.getTime()) ? null : date;
}

/** 相隔整天数（正 = `target` 在未来）。任一侧解析不出来返回 null。 */
export function daysUntil(target: string, from: Date = new Date()): number | null {
  const date = parseLocalDate(target);
  if (!date) return null;
  const start = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  return Math.round((date.getTime() - start.getTime()) / 86400_000);
}
