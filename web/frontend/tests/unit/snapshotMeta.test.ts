import { describe, expect, it } from "vitest";

import {
  canRestore,
  drillBadges,
  formatBytes,
  formatSnapshotTime,
  pendingChanges,
  toMillis,
} from "../../src/lib/snapshotMeta";

describe("toMillis", () => {
  it("后端给的秒（浮点）换算成毫秒并四舍五入", () => {
    expect(toMillis(1758645247)).toBe(1758645247000);
    expect(toMillis(1758645247.5)).toBe(1758645247500);
  });
});

describe("formatBytes", () => {
  it("按量级换挡（B / KB / MB）", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(940)).toBe("940 B");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1.0 KB");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(1024 * 1024)).toBe("1.0 MB");
    expect(formatBytes(3.5 * 1024 * 1024)).toBe("3.5 MB");
  });

  it("非法值不编造数字（返回空串，界面按「有则显示」处理）", () => {
    expect(formatBytes(Number.NaN)).toBe("");
    expect(formatBytes(-1)).toBe("");
  });
});

describe("formatSnapshotTime", () => {
  it("固定成 YYYY-MM-DD HH:mm（不随系统区域变，断言才落得下脚）", () => {
    const ms = new Date(2026, 8, 23, 22, 7).getTime();
    expect(formatSnapshotTime(ms)).toBe("2026-09-23 22:07");
  });

  it("月份 / 日期 / 分钟都补零", () => {
    const ms = new Date(2026, 0, 5, 9, 3).getTime();
    expect(formatSnapshotTime(ms)).toBe("2026-01-05 09:03");
  });

  it("坏时间戳返回空串", () => {
    expect(formatSnapshotTime(Number.NaN)).toBe("");
  });
});

describe("pendingChanges / canRestore", () => {
  it("变化 = 覆盖 + 补齐（「不变」不是变化）", () => {
    expect(pendingChanges({ overwrite: 2, add: 3 })).toBe(5);
    expect(pendingChanges({ overwrite: 0, add: 0 })).toBe(0);
  });

  it("空快照不放行（多半是坏包或来自一个空工作区）", () => {
    expect(canRestore({ overwrite: 0, add: 0, total: 0 })).toBe(false);
  });

  it("与当前完全一致时不放行（点下去只会得到一句「其实没变化」）", () => {
    expect(canRestore({ overwrite: 0, add: 0, total: 12 })).toBe(false);
  });

  it("只要有一个文件会变就放行", () => {
    expect(canRestore({ overwrite: 1, add: 0, total: 12 })).toBe(true);
    expect(canRestore({ overwrite: 0, add: 1, total: 12 })).toBe(true);
  });
});

describe("drillBadges", () => {
  it("跳过为 0 的项，保持覆盖 → 补齐 → 不变的顺序", () => {
    expect(drillBadges({ overwrite: 2, add: 0, same: 1 })).toEqual([
      { key: "overwrite", count: 2 },
      { key: "same", count: 1 },
    ]);
  });

  it("三项全 0 时返回空数组（由「无需还原」那句文案兜住）", () => {
    expect(drillBadges({ overwrite: 0, add: 0, same: 0 })).toEqual([]);
  });
});
