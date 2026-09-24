import { describe, expect, it } from "vitest";
import { gateBadgeVariant } from "../../src/components/badgeVariants";

/**
 * 硬门槛结论四态配色（评分放宽批）：
 * 「待补档案」（档案缺事实，要去补）与「待确认」（规则读不懂）必须不同色，
 * 否则用户分不清"是我要补档案"还是"规则读不懂"。
 */
describe("gateBadgeVariant（硬门槛四态配色）", () => {
  it("通过 / 不通过 保持既有语义色", () => {
    expect(gateBadgeVariant("通过")).toBe("success");
    expect(gateBadgeVariant("不通过")).toBe("destructive");
  });

  it("待补档案 → warning（琥珀：提示去补档案）", () => {
    expect(gateBadgeVariant("待补档案")).toBe("warning");
  });

  it("待确认与未知值 → outline 中性描边（不再吞进 warning）", () => {
    expect(gateBadgeVariant("待确认")).toBe("outline");
    expect(gateBadgeVariant(null)).toBe("outline");
    expect(gateBadgeVariant("某种未知文本")).toBe("outline");
  });
});
