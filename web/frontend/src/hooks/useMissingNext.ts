import { useEffect, useMemo, useState } from "react";
import { TERMINAL, type Application } from "../api";

// 「只看缺下一步」视图（v0.4.0-A）：进行中（非终态）却没填「下次动作」的记录。
//
// 自持"是否只看这一批"的开关，并顺手兜住一种空转：用户补齐最后几条后，
// 视图会停在空表格上——此时自动退出，把完整列表还回去。
export function useMissingNext(items: Application[]) {
  const [showMissingOnly, setShowMissingOnly] = useState(false);
  const missingNext = useMemo(
    () =>
      items.filter(
        (it) => !TERMINAL.includes(it.当前阶段) && !(it.下次动作 || "").trim()
      ),
    [items]
  );

  useEffect(() => {
    if (showMissingOnly && missingNext.length === 0) setShowMissingOnly(false);
  }, [showMissingOnly, missingNext.length]);

  return {
    showMissingOnly,
    setShowMissingOnly,
    missingNext,
    visibleItems: showMissingOnly ? missingNext : items,
  };
}
