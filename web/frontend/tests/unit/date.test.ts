import { describe, expect, it, vi } from "vitest";

import { daysUntil, parseLocalDate, todayISO } from "../../src/lib/date";

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

  it("returns null when the target cannot be parsed", () => {
    expect(daysUntil("")).toBeNull();
  });
});
