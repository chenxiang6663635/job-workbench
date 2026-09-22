import { useTranslation } from "react-i18next";

import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

// 勾选写回的确认框：摘要 + 「原行 / 新行」差异 + 确认 / 取消。
// 展示型组件——流程状态机在 NotesBrowser（本组件只画当前阶段、回抛两个动作）。
// 两段式纪律：确认按钮触发的是**凭令牌落盘**（apply），不是直接写文件。

// C-1：一次可以是一批行号（单行 = 长度 1 的列表——批量是唯一路径）。
export type ToggleFlow =
  | { phase: "previewing"; lines: number[] }
  | { phase: "confirm"; lines: number[]; token: string; summary: string; diff: string[] }
  | { phase: "applying"; lines: number[]; token: string; summary: string; diff: string[] };

export default function NotesToggleDialog({
  flow,
  onConfirm,
  onCancel,
}: {
  flow: ToggleFlow | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Dialog
      open={flow?.phase === "confirm" || flow?.phase === "applying"}
      onOpenChange={(open) => {
        // Esc / 点遮罩取消：只在确认阶段允许（落盘中不可关闭）
        if (!open && flow?.phase === "confirm") onCancel();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("notes.toggleTitle")}</DialogTitle>
          <DialogDescription>{t("notes.toggleHint")}</DialogDescription>
        </DialogHeader>
        {flow && "summary" in flow && (
          <div className="space-y-2">
            <p className="break-words text-sm font-medium text-foreground">{flow.summary}</p>
            {/* diff 是后端给的「原行 / 新行」两行文本：原样等宽展示，不做二次解析——
                解析错了比显示得丑危险得多（用户据此决定要不要落盘）。
                tabIndex：批量（C-1）之后它常常超过限高、成为**可滚动区域**——
                不可聚焦的话键盘用户看不全后半段（axe serious；单行 diff 不溢出，
                所以批量之前照不出这条）。 */}
            <pre
              tabIndex={0}
              aria-label={t("notes.toggleDiff")}
              className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground"
            >
              {flow.diff.join("\n")}
            </pre>
          </div>
        )}
        <DialogFooter>
          <Button onClick={onConfirm} disabled={flow?.phase === "applying"}>
            {flow?.phase === "applying" ? t("notes.toggleWriting") : t("notes.toggleConfirm")}
          </Button>
          <Button variant="ghost" onClick={onCancel} disabled={flow?.phase === "applying"}>
            {t("common.cancel")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
