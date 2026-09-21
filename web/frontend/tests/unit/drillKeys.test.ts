import { describe, expect, it } from "vitest";

import { drillKeyAction } from "../../src/lib/drillKeys";

// 训练面板键位（A-5）：判定是纯函数，拦截条件（修饰键 / 锁定态 / 确认卡）在这里钉死。
const key = (k: string, mods: Partial<{ ctrlKey: boolean; metaKey: boolean; altKey: boolean }> = {}) => ({
  key: k,
  ...mods,
});

const idle = { locked: false, hasPreview: false };

describe("drillKeyAction（键位 → 动作）", () => {
  it("空格与回车都是「看答案」", () => {
    expect(drillKeyAction(key(" "), idle)).toBe("reveal");
    expect(drillKeyAction(key("Enter"), idle)).toBe("reveal");
  });

  it("1 / 2 / 3 按按钮顺序映射三态自评", () => {
    expect(drillKeyAction(key("1"), idle)).toBe("grade:未看");
    expect(drillKeyAction(key("2"), idle)).toBe("grade:看过");
    expect(drillKeyAction(key("3"), idle)).toBe("grade:会了");
  });

  it("W（不分大小写）标错题、←→ 前后跳题（C-2 加回退）", () => {
    expect(drillKeyAction(key("w"), idle)).toBe("toggleWrong");
    expect(drillKeyAction(key("W"), idle)).toBe("toggleWrong");
    expect(drillKeyAction(key("ArrowRight"), idle)).toBe("next");
    expect(drillKeyAction(key("ArrowLeft"), idle)).toBe("prev");
  });

  it("修饰键组合一律不拦（Ctrl / Cmd / Alt 是浏览器与系统的）", () => {
    expect(drillKeyAction(key("1", { ctrlKey: true }), idle)).toBeNull();
    expect(drillKeyAction(key(" ", { ctrlKey: true }), idle)).toBeNull();
    expect(drillKeyAction(key("w", { metaKey: true }), idle)).toBeNull();
    expect(drillKeyAction(key("ArrowRight", { altKey: true }), idle)).toBeNull();
  });

  it("确认卡开着时只放 Esc（关掉它），动作键全部不响应", () => {
    const open = { locked: true, hasPreview: true };
    expect(drillKeyAction(key("Escape"), open)).toBe("cancelPreview");
    expect(drillKeyAction(key(" "), open)).toBeNull();
    expect(drillKeyAction(key("1"), open)).toBeNull();
    expect(drillKeyAction(key("w"), open)).toBeNull();
    expect(drillKeyAction(key("ArrowRight"), open)).toBeNull();
  });

  it("落盘请求在飞时连 Esc 都不响应（关掉卡拦不住已在路上的写入）", () => {
    const applying = { locked: true, hasPreview: true, busy: true };
    expect(drillKeyAction(key("Escape"), applying)).toBeNull();
  });

  it("没有确认卡时 Esc 不拦（交还浏览器）", () => {
    expect(drillKeyAction(key("Escape"), idle)).toBeNull();
    expect(drillKeyAction(key("Escape"), { locked: true, hasPreview: false })).toBeNull();
  });

  it("无关按键返回 null", () => {
    expect(drillKeyAction(key("q"), idle)).toBeNull();
    expect(drillKeyAction(key("4"), idle)).toBeNull();
    expect(drillKeyAction(key("ArrowUp"), idle)).toBeNull();
  });
});
