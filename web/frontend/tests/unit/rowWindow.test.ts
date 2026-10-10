import { describe, expect, it } from "vitest";

import { WINDOW_STEP, windowSlice } from "../../src/lib/rowWindow";

describe("windowSlice（长表窗口化）", () => {
  const many = Array.from({ length: 150 }, (_, i) => i);

  it("默认窗口 = 步长，remaining 是真实剩余", () => {
    const { visible, remaining } = windowSlice(many, WINDOW_STEP);
    expect(visible).toHaveLength(WINDOW_STEP);
    expect(visible[0]).toBe(0);
    expect(remaining).toBe(150 - WINDOW_STEP);
  });

  it("窗口小于步长时按步长渲染（防守：状态被重置成 0 也不空白）", () => {
    const { visible, remaining } = windowSlice(many, 0);
    expect(visible).toHaveLength(WINDOW_STEP);
    expect(remaining).toBe(150 - WINDOW_STEP);
  });

  it("窗口超过总数时全量渲染、remaining 归零", () => {
    const { visible, remaining } = windowSlice(many, 1000);
    expect(visible).toHaveLength(150);
    expect(remaining).toBe(0);
  });

  it("空表：不渲染、剩余 0（不是负数）", () => {
    expect(windowSlice([], 0)).toEqual({ visible: [], remaining: 0 });
    expect(windowSlice([], 999).remaining).toBe(0);
  });

  it("返回新数组、不改动输入", () => {
    const { visible } = windowSlice([1, 2, 3], WINDOW_STEP);
    expect(visible).not.toBe(many);
    expect(visible).toEqual([1, 2, 3]);
  });
});
