import { describe, expect, it } from "vitest";
import {
  clampFontSize,
  FONT_SIZE_DEFAULT,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
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
