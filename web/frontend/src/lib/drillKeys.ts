// 训练面板的键盘映射（2026-09-21）：把一次 keydown 翻译成「该做什么」。
//
// 为什么单独成文件：拦截条件（修饰键 / 锁定态 / 确认卡）是纯判定，正好落在
// vitest 的 node 环境单测里；组件只负责把动作接到既有的预览 / 落盘函数上
// （与 lib/drill.ts、lib/notes.ts 同款分层）。
//
// 「自评」动作带的是**状态数据值**（未看 / 看过 / 会了 就是 questions.csv 里的
// 真实取值，与 lib/drill.ts 的 WRONG_TAG 同源），不翻译——翻了三态枚举，键盘
// 映射就与后端拒绝 / 接受的那套字面量对不上了。

export type DrillKeyAction =
  | "reveal"
  | "grade:未看"
  | "grade:看过"
  | "grade:会了"
  | "toggleWrong"
  | "next"
  | "prev"
  | "cancelPreview";

/** 数字键 1 / 2 / 3 → 三态自评（顺序即按钮顺序） */
const GRADE_KEYS: DrillKeyAction[] = ["grade:未看", "grade:看过", "grade:会了"];

export interface DrillKeyState {
  /** 有动作正在进行（预览请求中 / 差异确认卡待处理）：除 Esc 外不接受按键 */
  locked: boolean;
  /** 差异确认卡是否开着——决定 Esc 是否有效 */
  hasPreview: boolean;
}

/**
 * 纯判定：返回该执行的动，或 null（不拦这次按键，交还浏览器）。
 *
 * 修饰键组合一律不拦（Ctrl / Cmd / Alt 是浏览器与系统的快捷键）；
 * 锁定态只放 Esc 过去——那正是"关掉确认卡"的路。
 */
export function drillKeyAction(
  event: { key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean },
  state: DrillKeyState
): DrillKeyAction | null {
  if (event.ctrlKey || event.metaKey || event.altKey) return null;
  if (event.key === "Escape") return state.hasPreview ? "cancelPreview" : null;
  if (state.locked) return null;
  if (event.key === " " || event.key === "Enter") return "reveal";
  if (event.key === "ArrowRight") return "next";
  if (event.key === "ArrowLeft") return "prev";
  if (event.key === "1" || event.key === "2" || event.key === "3") {
    return GRADE_KEYS[Number(event.key) - 1] ?? null;
  }
  if (event.key.toLowerCase() === "w") return "toggleWrong";
  return null;
}

/** 键盘焦点落在这些元素上时不该抢键（在输入框里打字 / 浏览器自己会"点"按钮）。 */
export const DRILL_KEY_IGNORE_SELECTOR =
  "input, textarea, select, [contenteditable='true'], button, a";
