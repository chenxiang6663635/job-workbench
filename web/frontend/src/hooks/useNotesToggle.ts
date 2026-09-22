// 笔记勾选写回的流程状态机（2026-09-21 从 NotesBrowser.tsx 拆出）。
//
// 拆出的理由有两个：① NotesBrowser 要同时装列表 / 选中 / 内容加载 / 位置记忆，
// 单文件逼近规模预算；②「预览 → 确认 → 落盘」是
// 自成一体的一段状态，整体搬走比在原文件里挤更清楚。
//
// 三条纪律不变：
// 1. **写通道只有一条**：预览签发令牌 → 凭令牌 POST /api/approvals/apply，不新增直写；
// 2. **同一时刻只有一个流程**：预览请求在飞 / 确认框开着时不再接新点击（并发预览会让
//    "点 A 弹出 B 的确认框"——那时勾选框整体禁用，编排侧用 locked 表达）；
// 3. **跨"切页签 / 刷新"只恢复 confirm 态**：previewing 的预览请求与 applying 的
//    落盘都是组件内的 promise，组件一卸载就作废，恢复它们只会得到一个永远不落地的
//    确认框（而且整篇勾选框被 locked 卡死）。令牌十分钟过期，过期由服务端拒绝。
//
// C-1 批量：多一条**待提交集合**（pending）——批量模式下点选只翻本地集合（不发
// 请求），点「提交」才把整批送进同一条两段式通道（一次预览列出全部将翻转的行、
// 一次确认全部落盘）。集合落 sessionStorage：10s 指纹轮询会整页 reload、切页签
// 也卸载组件，只放 useState 的话"勾到一半"会全丢（drill 轮次的先例同因）。

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { ToggleFlow } from "../components/NotesToggleDialog";
import type { NotesActive } from "../lib/notes";
import {
  clearToggleSnapshot,
  readPendingLines,
  readToggleSnapshot,
  togglePendingLine,
  writePendingLines,
  writeToggleSnapshot,
} from "../lib/notesView";

export function useNotesToggle(
  ws: string,
  active: NotesActive | null,
  /** 落盘成功后回调（编排侧据此重拉正文） */
  onApplied: () => void
) {
  const [flow, setFlow] = useState<ToggleFlow | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [batchMode, setBatchMode] = useState(false);
  const [pending, setPending] = useState<number[]>([]);

  // 切文件 = 换键：各文件各自记住自己的集合（不是清空——集合是廉价可重建的
  // 本地态，但勾了一半就丢很烦）
  const fileKey = active ? `${active.section}::${active.rel}` : null;
  // pending 的最新值另存 ref：动作回调要拿它算下一态，而又不该把「集合变化」塞进
  // useCallback 依赖（那会让整篇正文跟着重渲染）
  const pendingRef = useRef<number[]>([]);

  /** 集合的唯一写入口：更新内存 + 落**当前文件**的键。
   *
   * 为什么不跟着 pending 用 effect 写：键切换那一帧 effect 里的 `pending` 还是
   * 上一个文件的值，会把 A 的集合写进 B 的键（切回来像"凭空多选了三项"）。
   * 动作驱动没有这个窗口——集合只在用户动作（点选 / 清空 / 落盘后）时落盘。 */
  const updatePending = useCallback(
    (next: number[]) => {
      pendingRef.current = next;
      setPending(next);
      if (!ws || !fileKey) return;
      const [section, rel] = fileKey.split("::");
      writePendingLines(ws, section, rel, next);
    },
    [ws, fileKey]
  );

  // 切键（含首次挂载）：读回该文件自己的集合
  useEffect(() => {
    if (!ws || !fileKey) return;
    const [section, rel] = fileKey.split("::");
    const saved = readPendingLines(ws, section, rel);
    pendingRef.current = saved;
    setPending(saved);
  }, [ws, fileKey]);

  const onToggleTask = useCallback(
    (line: number) => {
      if (!active || flow) return;
      setToggleError(null);
      // 批量模式：点选只翻本地集合（一次请求都不发——"打勾"的反馈是即时的）
      if (batchMode) {
        updatePending(togglePendingLine(pendingRef.current, line));
        return;
      }
      const lines = [line];
      setFlow({ phase: "previewing", lines });
      api
        .previewPrepToggle(active.section, active.rel, lines)
        .then((p) =>
          setFlow({
            phase: "confirm",
            lines,
            token: p.token,
            summary: p.summary,
            diff: p.diff,
          })
        )
        .catch((e: Error) => {
          setFlow(null);
          setToggleError(e.message);
        });
    },
    [active, flow, batchMode, updatePending]
  );

  /** 把待提交集合整批送进同一条两段式通道（一次预览、一次确认）。 */
  const onBatchSubmit = useCallback(() => {
    if (!active || flow || !pending.length) return;
    const lines = [...pending].sort((a, b) => a - b);
    setToggleError(null);
    setFlow({ phase: "previewing", lines });
    api
      .previewPrepToggle(active.section, active.rel, lines)
      .then((p) =>
        setFlow({
          phase: "confirm",
          lines,
          token: p.token,
          summary: p.summary,
          diff: p.diff,
        })
      )
      .catch((e: Error) => {
        setFlow(null);
        setToggleError(e.message);
      });
  }, [active, flow, pending]);

  const onToggleBatchMode = useCallback(() => {
    // 退出批量模式：集合失去意义（它只在批量模式下可累积），一并清掉
    if (batchMode) updatePending([]);
    setBatchMode((prev) => !prev);
  }, [batchMode, updatePending]);

  const onClearPending = useCallback(() => updatePending([]), [updatePending]);

  const onConfirmToggle = useCallback(() => {
    if (!flow || flow.phase !== "confirm") return;
    const { lines, token, summary, diff } = flow;
    setFlow({ phase: "applying", lines, token, summary, diff });
    api
      .applyApproval(token)
      .then(() => {
        setFlow(null);
        updatePending([]);
        setBatchMode(false);
        onApplied();
      })
      .catch((e: Error) => {
        setFlow(null);
        setToggleError(e.message);
      });
  }, [flow, onApplied, updatePending]);

  const onCancelToggle = useCallback(() => setFlow(null), []);
  const clearToggleError = useCallback(() => setToggleError(null), []);

  // 恢复（只做一次）：文件确认下来之后，把上一轮待确认的那一步接回来
  const restored = useRef(false);
  useEffect(() => {
    if (!active) return;
    const snapshot = readToggleSnapshot(ws);
    const sameFile = snapshot?.section === active.section && snapshot?.rel === active.rel;
    if (snapshot && !sameFile) clearToggleSnapshot();
    if (restored.current) return;
    restored.current = true;
    if (!snapshot || !sameFile) return;
    setFlow({
      phase: "confirm",
      lines: snapshot.lines,
      token: snapshot.token,
      summary: snapshot.summary,
      diff: snapshot.diff,
    });
  }, [active, ws]);

  // 落记忆：confirm / applying 存，其余（previewing / null）清
  useEffect(() => {
    if (!active) return;
    if (flow?.phase === "confirm" || flow?.phase === "applying") {
      writeToggleSnapshot({
        ws,
        section: active.section,
        rel: active.rel,
        lines: flow.lines,
        token: flow.token,
        summary: flow.summary,
        diff: flow.diff,
      });
    } else {
      clearToggleSnapshot();
    }
  }, [flow, active, ws]);

  return {
    flow,
    toggleError,
    clearToggleError,
    onToggleTask,
    onConfirmToggle,
    onCancelToggle,
    batchMode,
    pending,
    onToggleBatchMode,
    onBatchSubmit,
    onClearPending,
  };
}
