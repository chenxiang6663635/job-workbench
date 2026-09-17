import { describe, expect, it } from "vitest";
import { cn } from "../../src/lib/utils";

/**
 * 前端单元测试的起点（2026-09-16 治理批）：先守住**纯逻辑可测、可回归**这
 * 条最小面——此前 691 条测试全是 Python，前端只有 50 条 Playwright e2e，
 * 像「类名冲突谁覆盖谁」这种一行逻辑只能靠肉眼。
 *
 * 单测刻意放在 `tests/unit/`（与 `e2e/` 平行、都在 `src/` 之外）：
 * 这里的中文是**测试数据与用例说明**，不是界面文案，不该进 i18n 硬编码扫描。
 */
describe("cn（类名合并）", () => {
  it("条件类交给 clsx：false / undefined / null 不产出", () => {
    const hidden = false; // 走变量：字面量 `false && x` 会被 eslint 判为常量表达式
    expect(cn("a", hidden && "b", undefined, null, "c")).toBe("a c");
  });

  it("Tailwind 冲突类由后者覆盖——批 4 起全站靠它做状态色与强调色取舍", () => {
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("不冲突的类原样保留", () => {
    expect(cn("flex", "gap-2", "text-primary")).toBe("flex gap-2 text-primary");
  });

  it("对象与数组写法也可用（clsx 的形态）", () => {
    expect(cn(["a", "b"], { c: true, d: false })).toBe("a b c");
  });
});
