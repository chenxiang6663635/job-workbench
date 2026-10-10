import { useEffect, useState } from "react";

import { WINDOW_STEP, windowSlice } from "../lib/rowWindow";

/**
 * 列表窗口化（长表渲染量护栏）。
 *
 * 窗口在**列表身份变化**时回到第一屏：筛选 / 排序 / 重新取数都会换一个新数组，
 * 沿用旧窗口会让「刚筛完只剩两条却显示 120 条的位置」这种错位状态存在。
 * 取数在调用方（受控组件纪律）：本 hook 只碰渲染量，不碰数据。
 */
export function useRowWindow<T>(items: T[], step = WINDOW_STEP) {
  const [shown, setShown] = useState(step);

  useEffect(() => setShown(step), [items, step]);

  const { visible, remaining } = windowSlice(items, shown, step);
  return {
    visible,
    remaining,
    showMore: () => setShown((n) => n + step),
  };
}
