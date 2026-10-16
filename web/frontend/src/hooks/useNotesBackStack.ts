// 笔记返回栈的组件侧接线（issue #274 三期）。
//
// 为什么单独成 hook：NotesBrowser 同时装列表 / 选中 / 内容加载 / 位置记忆 / 写回编排，
// 本就逼近规模预算（useNotesToggle 拆出去时同因）；而"进新一篇之前压栈、出栈拿到落点"
// 是自成一体的一段状态。纯逻辑（入栈 / 出栈 / 上限 / 脏值解析 / 存储）在
// lib/notesStack.ts，这里只管把 React 状态与那条存储接起来。
//
// 分工的边界：hook 只做"记路"与"取路"，**落点怎么落地归调用方**——切 active、清写回
// 残留、更新「上次打开」都是 NotesBrowser 的既有收尾，由 `backTo(land)` 回调带进来，
// 不在这里重写一遍。

import { useCallback, useEffect, useState } from "react";

import type { NotesActive } from "../lib/notes";
import {
  popStack,
  pushStack,
  readNotesStack,
  rememberFrom,
  writeNotesStack,
} from "../lib/notesStack";
import { captureNotesPos } from "../lib/notesView";

export interface NotesBackStack {
  /** 栈顶 = 「返回上一篇」的目标；栈空为 null（入口据此不渲染） */
  previous: NotesActive | null;
  /**
   * 进新一篇**之前**调用，带上落点：把当前这一篇压栈（三条进入路径共用＝「统一入栈」）。
   * 落点与当前同一篇时不动——"点的是当前这一篇"没有上一篇可退。
   */
  remember: (next: NotesActive) => void;
  /** 出栈并把落点交给 `land` 落地；栈空时什么都不做（调用方不必自己判空） */
  backTo: (land: (target: NotesActive) => void) => void;
}

export function useNotesBackStack(ws: string, active: NotesActive | null): NotesBackStack {
  // 从 sessionStorage 起步：切页签会**卸载**本组件（A-6 同因），不记的话"去宣讲会
  // 看一眼再回来"就把走过的路全丢了；整页 reload（外部编辑指纹）同理。
  const [entries, setEntries] = useState<NotesActive[]>(() => readNotesStack(ws));

  // 状态变即写——与 writeNotesUi 同一套范式，不另造存储
  useEffect(() => {
    writeNotesStack(ws, entries);
  }, [ws, entries]);

  const remember = useCallback(
    (next: NotesActive) => {
      const from = rememberFrom(active, next);
      if (!from) return;
      // 顺手把**离开时的阅读位置**写进既有位置槽（captureNotesPos 读的是当前 DOM）：
      // 返回时 NotesReader 的位置恢复照旧生效，落回你走时那一屏——无需新存储。
      captureNotesPos(ws, from.section, from.rel);
      setEntries((prev) => pushStack(prev, from));
    },
    [active, ws]
  );

  const backTo = useCallback(
    (land: (target: NotesActive) => void) => {
      const { previous: target, rest } = popStack(entries);
      if (!target) return;
      setEntries(rest);
      land(target);
    },
    [entries]
  );

  return {
    previous: entries.length ? entries[entries.length - 1] : null,
    remember,
    backTo,
  };
}
