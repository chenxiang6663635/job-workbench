import { useCallback, useEffect, useRef, useState } from "react";

import { announce } from "../lib/announce";

/**
 * 撤销窗口（毫秒）。
 *
 * 5 秒是本仓口径，来源是 Marigold 设计系统对破坏性动作的四问判据：动作若是
 * 单项的、后果可见的、对象可辨的、可以延迟一点的——就给撤销窗口；四项里任何
 * 一项不成立就给确认框。两者**绝不同时给**（同时给会让用户把确认框当形式点过去，
 * 反过来削弱所有确认框）。
 */
export const UNDO_WINDOW_MS = 5000;

export interface UndoRequest {
  /** 已翻译的提示语（容器文案由调用方传，是本仓 i18n 纪律） */
  message: string;
  /** 立即执行的动作：视觉与状态先变，用户马上看得到；不传则走"延迟提交" */
  apply?: () => void;
  /** 撤销时要恢复到的状态（`apply` 模式必给） */
  revert?: () => void;
  /** "延迟提交"模式的落盘动作：窗口期内不动磁盘，到点才执行 */
  commit?: () => void;
}

/**
 * 需要"后悔药"的动作统一走这里：即时生效 + 5 秒撤销，或延迟提交 + 到点落盘。
 *
 * 两种模式的取舍：视觉即时反馈优先的（字号、主题这类外观项）用 `apply` + `revert`；
 * 只有"写下去才看得见"的（表格式偏好）用 `commit` 延迟落盘，撤销就等于没发生过。
 */
export function useUndoableAction(windowMs: number = UNDO_WINDOW_MS) {
  const [pending, setPending] = useState<{ message: string } | null>(null);
  const timerRef = useRef<number | null>(null);
  const actionRef = useRef<UndoRequest | null>(null);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  /** 把未决动作落定：窗口到期、被新动作顶替、组件卸载，三种情况都走它。 */
  const settle = useCallback(() => {
    clearTimer();
    const request = actionRef.current;
    actionRef.current = null;
    setPending(null);
    // 已 apply 的动作不再提交（apply 就是落点）；延迟提交的在这里才写下去
    if (request?.commit) request.commit();
  }, []);

  const run = useCallback(
    (request: UndoRequest) => {
      // 同一时刻只留一个未决动作：上一个**落定**而不是丢弃——用户点过就该生效
      settle();
      actionRef.current = request;
      request.apply?.();
      setPending({ message: request.message });
      announce(request.message);
      timerRef.current = window.setTimeout(settle, windowMs);
    },
    [settle, windowMs],
  );

  const undo = useCallback(() => {
    clearTimer();
    const request = actionRef.current;
    actionRef.current = null;
    setPending(null);
    request?.revert?.();
  }, []);

  // 卸载时落定未决动作：用户既然点了，就不该因为切页而静默丢掉（禁静默吞错）
  useEffect(() => settle, [settle]);

  return { pending, run, undo, settle };
}
