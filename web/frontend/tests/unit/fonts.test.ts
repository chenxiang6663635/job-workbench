import { describe, expect, it } from "vitest";
import {
  clampFontSize,
  normalizeNumericId,
  DEFAULT_NUMERIC_ID,
  FONT_SIZE_DEFAULT,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  NUMERICS,
} from "../../src/lib/fonts";

/**
 * 界面字号连续化（2026-09-17 实测反馈批）：clampFontSize 是纯函数——滑块值、
 * 存储值与历史档迁移都汇到它这一处，先把边界行为钉住（改坏即红）。
 * 单测刻意放在 `tests/unit/`（与 `e2e/` 平行、都在 `src/` 之外）：
 * 这里的中文是**测试数据与用例说明**，不是界面文案，不进 i18n 硬编码扫描。
 */
describe("clampFontSize（界面字号的吸附与夹取）", () => {
  it("吸附到 5% 步进（就近取整）", () => {
    expect(clampFontSize(113)).toBe(115);
    expect(clampFontSize(112)).toBe(110);
  });

  it("越界夹到 [80, 150]", () => {
    expect(clampFontSize(50)).toBe(FONT_SIZE_MIN);
    expect(clampFontSize(200)).toBe(FONT_SIZE_MAX);
  });

  it("非法值（NaN / ±Infinity）回落默认 100", () => {
    expect(clampFontSize(Number.NaN)).toBe(FONT_SIZE_DEFAULT);
    expect(clampFontSize(Number.POSITIVE_INFINITY)).toBe(FONT_SIZE_DEFAULT);
    expect(clampFontSize(Number.NEGATIVE_INFINITY)).toBe(FONT_SIZE_DEFAULT);
  });

  it("默认值本身在步进网格上，原样通过", () => {
    expect(clampFontSize(FONT_SIZE_DEFAULT)).toBe(FONT_SIZE_DEFAULT);
  });
});

/**
 * 数字槽归一化（批 4.6）：存储值、首帧脚本与设置页三处的输入都汇到
 * normalizeNumericId 这一处——未登记 id / 空串一律回落默认款（不落空槽）。
 * "follow"（跟随界面字体）是合法值，必须原样通过（它是关闭数字槽的显式开关）。
 */
describe("normalizeNumericId（数字槽归一化）", () => {
  it("合法 id 原样通过（含 follow）", () => {
    expect(normalizeNumericId("plex-mono")).toBe("plex-mono");
    expect(normalizeNumericId("follow")).toBe("follow");
  });

  it("未登记 id 与空串回落默认款", () => {
    expect(normalizeNumericId("comic-sans")).toBe(DEFAULT_NUMERIC_ID);
    expect(normalizeNumericId("")).toBe(DEFAULT_NUMERIC_ID);
  });

  it("默认款在候选列表里（默认与列表防漂移）", () => {
    expect(NUMERICS.map((n) => n.id)).toContain(DEFAULT_NUMERIC_ID);
  });
});
