// 笔记正文里的任务勾选框（2026-09-21 从 NotesMarkdown 拆出）。
//
// 拆出的理由与 prep_toggle 同款：NotesMarkdown 已经装满"块 → 元素"的映射表，
// 再加批量勾选（C-1）的待提交视觉就顶到规模预算了；勾选框是自成一体的一段
// （行号上下文 + 可点性 + 三态视觉），整体搬走比在原文件里挤更清楚。

import { useContext, type InputHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "../lib/utils";
import { TaskLineContext } from "./notesTaskLine";

export function TaskCheckbox({
  checked,
  onToggle,
  pendingLine,
  queuedLines,
  locked,
  ...props
}: {
  checked?: boolean;
  onToggle?: (line: number) => void;
  /** 正在预览的行号——该项呈 pending 禁用态 */
  pendingLine: number | null;
  /** 批量待提交的行号（C-1）：本地即时翻转 + 高亮环，表示"还没落盘" */
  queuedLines?: number[];
  /** 有写回流程在进行中：整篇勾选框都禁用（避免连点时"点 A 弹出 B 的确认框"） */
  locked?: boolean;
} & InputHTMLAttributes<HTMLInputElement>) {
  const { t } = useTranslation();
  const line = useContext(TaskLineContext);
  // 有回调且行号可定位才可点击；否则退回只读展示（缺任一条件都不写）。
  // aria-label 走 t()——它是 form 元素，axe 的 label 规则要求可访问名称
  // （disabled 也不例外），且文案要能翻译。
  const interactive = onToggle != null && line != null;
  const pending = interactive && pendingLine === line;
  // 批量：点选即本地翻转（"打勾"的反馈是即时的），高亮环说明它还没写进文件
  const queued = interactive && line != null && !!queuedLines?.includes(line);
  return (
    <input
      type="checkbox"
      checked={queued ? !checked : checked}
      {...props}
      data-queued={queued ? "true" : undefined}
      readOnly={!interactive}
      // 展开之后再写 disabled / onChange：GFM 生成的 props 里带 disabled:true，
      // 放前面会被它覆盖（那是只读批的形态，写回批要能点）。
      disabled={!interactive || pending || locked}
      onChange={interactive ? () => onToggle?.(line) : undefined}
      aria-label={t("notes.checkboxLabel")}
      className={cn(
        "mr-2 h-4 w-4 accent-primary align-middle",
        interactive && !pending && "cursor-pointer",
        // 待提交（批量）：高亮环说明"这一项还没写进文件"
        queued && "rounded ring-2 ring-primary/60"
      )}
    />
  );
}
