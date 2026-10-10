// 长表的**窗口化**：一次只渲染窗口内的行，「显示更多」按步长放大窗口。
//
// 为什么不是真虚拟化：追踪表有粘性表头 + 可展开的时间线行，按行高估算的窗口
// 在展开时会错位；本地单用户的数据量级（数百行）用「多渲染几十行」已经足够，
// 且不引依赖、不动表结构（仍是普通 table：Ctrl+F、打印、屏幕阅读器都正常）。
//
// 抽成纯函数（而不是把状态塞进 hook）：切片与剩余量是**唯一**值得钉的算术，
// 单测在 `tests/unit/rowWindow.test.ts`；状态归 `hooks/useRowWindow`。
export const WINDOW_STEP = 60;

export function windowSlice<T>(items: T[], shown: number, step = WINDOW_STEP) {
  const total = items.length;
  // 下限取 step（状态被外部重置成 0 时仍渲染第一屏），上限取 total（不越界）
  const limit = Math.min(Math.max(shown, step), total);
  return { visible: items.slice(0, limit), remaining: Math.max(total - limit, 0) };
}
