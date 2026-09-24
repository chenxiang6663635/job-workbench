import { Undo2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Button } from "./ui/button";

interface UndoBarProps {
  /** 已翻译的提示语（如「已还原默认字号」）——容器文案由调用方传 */
  message: string;
  onUndo: () => void;
}

/**
 * 底部居中的撤销条（配合 `hooks/useUndoableAction.ts`）。
 *
 * 为什么不用 toast 库：本仓零新依赖，而"一条能点撤销的提示"总共二十行。为什么不走
 * `role="status"`：它里面有可聚焦的按钮，读屏会把按钮文本一起念得乱七八糟——播报
 * 交给既有的 `lib/announce` + `LiveRegion`（钩子里已经发了），这里只负责可见与可点。
 */
export default function UndoBar({ message, onUndo }: UndoBarProps) {
  const { t } = useTranslation();
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center px-4">
      <div
        role="group"
        aria-label={t("common.undo")}
        className="pointer-events-auto flex max-w-full items-center gap-3 rounded-lg bg-popover px-4 py-2 shadow-lg ring-1 ring-border"
      >
        <span className="truncate text-xs text-popover-foreground">{message}</span>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 shrink-0 gap-1 px-2 text-xs"
          onClick={onUndo}
        >
          <Undo2 size={12} aria-hidden="true" />
          {t("common.undo")}
        </Button>
      </div>
    </div>
  );
}
