import { describe, expect, it, vi } from "vitest";

import { daysUntil, formatMailDate, parseLocalDate, todayISO } from "../../src/lib/date";

describe("todayISO", () => {
  it("returns the local calendar day, not the UTC one", () => {
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    expect(todayISO()).toBe(
      `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`,
    );
  });

  it("reports the local date even in the small hours (UTC+8 used to land on yesterday)", () => {
    vi.useFakeTimers();
    // 本地凌晨 2 点：任何把 UTC 当日历日的写法（`toISOString().slice(0, 10)`）
    // 在东八区都会给出"昨天"，写进追踪表就是错一天
    vi.setSystemTime(new Date(2026, 8, 30, 2, 0, 0));
    expect(todayISO()).toBe("2026-09-30");
    vi.useRealTimers();
  });

  it("round-trips back through parseLocalDate to the same local day", () => {
    const parsed = parseLocalDate(todayISO());
    const now = new Date();
    expect(parsed?.getFullYear()).toBe(now.getFullYear());
    expect(parsed?.getMonth()).toBe(now.getMonth());
    expect(parsed?.getDate()).toBe(now.getDate());
  });
});

describe("parseLocalDate", () => {
  it("parses YYYY-MM-DD at local midnight", () => {
    expect(parseLocalDate("2026-09-30")?.getTime()).toBe(
      new Date(2026, 8, 30).getTime(),
    );
  });

  it("parses YYYY-MM-DD HH:mm", () => {
    expect(parseLocalDate("2026-09-30 14:30")?.getTime()).toBe(
      new Date(2026, 8, 30, 14, 30).getTime(),
    );
  });

  it("returns null for blank or unparsable input", () => {
    expect(parseLocalDate("")).toBeNull();
    expect(parseLocalDate("   ")).toBeNull();
    expect(parseLocalDate("不是日期")).toBeNull();
  });

  // 批末独立审查：这条是与后端同口径的**判据性**用例——`Date` 会把日历上不存在
  // 的日子默默进位（`2026-02-31` → 3 月 3 日），那是"解析成功"的假象；后端
  // `check_date` 早就在拒它，前端若接受，offer 的"3 天内到期"提醒就会基于一个
  // 不存在的日子亮起。
  it("rejects days that do not exist on the calendar", () => {
    expect(parseLocalDate("2026-02-31")).toBeNull();
    expect(parseLocalDate("2026-13-01")).toBeNull();
    expect(parseLocalDate("2026-04-31 10:00")).toBeNull();
  });
});

describe("daysUntil", () => {
  it("counts whole days from today's local midnight", () => {
    const today = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const sameDay = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(
      today.getDate(),
    )}`;
    expect(daysUntil(sameDay)).toBe(0);

    const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
    expect(daysUntil(`${tomorrow.getFullYear()}-${pad(tomorrow.getMonth() + 1)}-${pad(
      tomorrow.getDate(),
    )}`)).toBe(1);
  });

  it("counts calendar days even when the target carries a clock", () => {
    // 只看日历日：当天 23:00 应当回答 0，而不是"还差 1 天"
    const from = new Date(2026, 8, 30, 10, 0, 0);
    expect(daysUntil("2026-09-30 23:00", from)).toBe(0);
    expect(daysUntil("2026-10-03 23:00", from)).toBe(3);
  });

  it("returns null when the target cannot be parsed", () => {
    expect(daysUntil("")).toBeNull();
    expect(daysUntil("2026-02-31", new Date(2026, 8, 30, 10))).toBeNull();
  });
});

describe("formatMailDate", () => {
  // 2026-09-25 真机：IMAP 的 Date 头是 RFC 2822 原文，而解析建议那条链路原样把它
  // 透传给后端 → 后端拿不到日期 → 「3 天内」按今天算（"还有 3 天"，实际已过期）。
  // 这条用例钉的是"前端必须交出后端与 CSV 都认的那个形状"。
  it("normalizes the RFC 2822 Date header to the CSV shape", () => {
    const raw = "Sun, 20 Sep 2026 09:05:00 +0800";
    const d = new Date(raw);
    const pad = (n: number) => String(n).padStart(2, "0");
    expect(formatMailDate(raw)).toBe(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
        `${pad(d.getHours())}:${pad(d.getMinutes())}`,
    );
  });

  it("keeps an already-CSV value untouched", () => {
    expect(formatMailDate("2026-09-16 10:00")).toBe("2026-09-16 10:00");
  });

  it("returns blank for blank input (no invented date)", () => {
    expect(formatMailDate("")).toBe("");
    expect(formatMailDate(undefined)).toBe("");
  });

  it("falls back to the raw text when nothing parses (honest over pretty)", () => {
    expect(formatMailDate("日期未知")).toBe("日期未知");
  });
});
