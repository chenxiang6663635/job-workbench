// 笔记勾选写回的流程状态机（2026-09-21 从 NotesBrowser.tsx 拆出）。
//
// 拆出的理由有两个：① NotesBrowser 要同时装列表 / 选中 / 内容加载 / 位置记忆，
// 而批量写回（C-1）还要再加选择态——规模预算不允许；②「预览 → 确认 → 落盘」是
// 自成一体的一段状态，整体搬走比在原文件里挤更清楚。
//
// 三条纪律不变：
// 1. **写通道只有一条**：预览签发令牌 → 凭令牌 POST /api/approvals/apply，不新增直写；
// 2. **同一时刻只有一个流程**：预览请求在飞 / 确认框开着时不再接新点击（并发预览会让
//    "点 A 弹出 B 的确认框"——那时勾选框整体禁用，编排侧用 locked 表达）；
// 3. **跨"切页签 / 刷新"只恢复 confirm 态**：previewing 的预览请求与 applying 的
//    落盘都是组件内的 promise，组件一卸载就作废，恢复它们只会得到一个永远不落地的
//    确认框（而且整篇勾选框被 locked 卡死）。令牌十分钟过期，过期由服务端拒绝。

import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../api";
import type { ToggleFlow } from "../components/NotesToggleDialog";
import type { NotesActive } from "../lib/notes";
import { clearToggleSnapshot, readToggleSnapshot, writeToggleSnapshot } from "../lib/notesView";

export function useNotesToggle(
  ws: string,
  active: NotesActive | null,
  /** 落盘成功后回调（编排侧据此重拉正文） */
  onApplied: () => void
) {
  const [flow, setFlow] = useState<ToggleFlow | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  const onToggleTask = useCallback(
    (line: number) => {
      if (!active || flow) return;
      setToggleError(null);
      setFlow({ phase: "previewing", line });
      api
        .previewPrepToggle(active.section, active.rel, line)
        .then((p) =>
          setFlow({ phase: "confirm", line, token: p.token, summary: p.summary, diff: p.diff })
        )
        .catch((e: Error) => {
          setFlow(null);
          setToggleError(e.message);
        });
    },
    [active, flow]
  );

  const onConfirmToggle = useCallback(() => {
    if (!flow || flow.phase !== "confirm") return;
    const { line, token, summary, diff } = flow;
    setFlow({ phase: "applying", line, token, summary, diff });
    api
      .applyApproval(token)
      .then(() => {
        setFlow(null);
        onApplied();
      })
      .catch((e: Error) => {
        setFlow(null);
        setToggleError(e.message);
      });
  }, [flow, onApplied]);

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
      line: snapshot.line,
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
        line: flow.line,
        token: flow.token,
        summary: flow.summary,
        diff: flow.diff,
      });
    } else {
      clearToggleSnapshot();
    }
  }, [flow, active, ws]);

  return { flow, toggleError, clearToggleError, onToggleTask, onConfirmToggle, onCancelToggle };
}
