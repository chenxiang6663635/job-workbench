// 任务项行号（1-based 源码行）的上下文：li 写入、TaskCheckbox 读取——同一次
// 渲染、同一棵树（GFM 的 input 由 hast 直接构造、没有 position，行号只能从
// 包着它的 li 传下来）。
//
// 单独放一个文件是因为 react-refresh 要求"一个文件只导出组件"：与
// TaskCheckbox 同文件会让整块的热更新失效。

import { createContext } from "react";

export const TaskLineContext = createContext<number | null>(null);
