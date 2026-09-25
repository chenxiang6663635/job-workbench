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
  if (Number.isNaN(date.getTime())) return null;
  // `Date` 会把日历上不存在的日子**进位**（`2026-02-31` → 3 月 3 日），而它并不等于
  // 输入——那是「解析成功」的假象。回比一次，不等就按"解析不出来"处理（与后端
  // `check_date` 的判定同一条线：正则形状过了不代表这个日子真实存在）。
  if (
    date.getFullYear() !== Number(y) ||
    date.getMonth() !== Number(m) - 1 ||
    date.getDate() !== Number(d)
  ) {
    return null;
  }
  return date;
}

/**
 * 相隔整天数（正 = `target` 在未来）。任一侧解析不出来返回 null。
 *
 * 只看**日历日**：`target` 带时刻也归零到当天（`daysUntil("2026-09-30 23:00")`
 * 在 9 月 30 日当天应当回答 0，而不是"还差 1 天"）。
 */
export function daysUntil(target: string, from: Date = new Date()): number | null {
  const date = parseLocalDate(target);
  if (!date) return null;
  const start = new Date(from.getFullYear(), from.getMonth(), from.getDate());
  const end = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  return Math.round((end.getTime() - start.getTime()) / 86400_000);
}

/** `YYYY-MM-DD HH:mm`（本模块唯一的时间戳形状，写回与显示共用）。 */
function stamp(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

/**
 * 邮件日期（IMAP 的 `Date` 头）→ CSV 既有的 `YYYY-MM-DD HH:mm`。
 *
 * `Date` 头是 RFC 2822 原文（`Sun, 20 Sep 2026 09:05:00 +0800`），而它要去三处，
 * 口径必须同一份：写进 `mails.csv` 的「日期」列（不转会让导入行与手工行混排后
 * 「日期倒序」失序，审查 m-1）、作为解析建议的时长基准、界面显示。此前这三处
 * 各写各的，其中「时长基准」那条路干脆没转（后端拿不到日期 → 按今天算，
 * 2026-09-25 真机）。后端 `mail_dates.coerce_date` 现在两种形态都认，这里统一
 * 转换只是为了同一个日期不再有两种长相。
 *
 * 解析失败退回原文：宁可显示得难看，也不猜一个日期（与 `parseLocalDate` 的
 * "不拿 Invalid Date 去比较"同一条线）。
 */
export function formatMailDate(raw: string | undefined | null): string {
  const text = (raw || "").trim();
  if (!text) return "";
  // 已经是 CSV 口径：原样返回，不再过一次 `new Date(string)`——那条路对
  // `2026-09-16 10:00` 这类非 ISO 形态在浏览器间不一致，且没必要改写既有值。
  if (parseLocalDate(text)) return text;
  // RFC 2822（IMAP 的 Date 头）：各浏览器都支持这一形态；带时区偏移时按本地呈现，
  // 与 CSV 里手工输入的本地时间口径一致。
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? text : stamp(parsed);
}
