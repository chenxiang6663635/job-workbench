import { describe, expect, it } from "vitest";
import { domainLabel } from "../../src/lib/domainLabels";

/**
 * 枚举展示层的回退契约：**未登记的值必须原样返回**。
 *
 * 这是数据完整性的最后一道保险——阶段/批次/档位的「值」是 CSV 与 CLI 的真值，
 * 显示层只能翻译，绝不许改值；一旦这里改成返回 key 名或抛错，界面就会把
 * `domain.stage.九面` 之类的东西漏给用户。
 *
 * 放在 `tests/unit/`（不在 `src/` 下）：用例里的中文是被测数据与说明，
 * 不是界面文案——挪到这里就不必为它登记 i18n 豁免（登记会随注释改动而腐化）。
 */

// 假 t：只认 domain.<组>.<值> 这一支，未登记时按 defaultValue 回落
// （与 i18next 的 defaultValue 行为同形）
const dict: Record<string, string> = {
  "domain.stage.一面": "Round 1",
  "domain.tier.强烈投": "Apply strongly",
};
const fakeT = ((key: string, opts?: { defaultValue?: string }) =>
  key in dict ? dict[key] : (opts?.defaultValue ?? key)) as never;

describe("domainLabel", () => {
  it("登记过的组/值 → 当前语言文案", () => {
    expect(domainLabel("stage", "一面", fakeT)).toBe("Round 1");
    expect(domainLabel("tier", "强烈投", fakeT)).toBe("Apply strongly");
  });

  it("未登记的值原样返回（新枚举、用户自填轮次）", () => {
    expect(domainLabel("stage", "九面", fakeT)).toBe("九面");
    expect(domainLabel("round", "某个自填轮次", fakeT)).toBe("某个自填轮次");
  });

  it("空值直接返回，不查翻译表", () => {
    expect(domainLabel("stage", "", fakeT)).toBe("");
  });

  it("中文真值在英文界面下也走同一条路径（值不变，只换展示）", () => {
    expect(domainLabel("batch", "正式批", fakeT)).toBe("正式批");
  });
});
