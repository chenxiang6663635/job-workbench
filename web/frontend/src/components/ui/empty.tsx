import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

// 空态原语（批 4）：三态规范里的 Empty——「图形 + 一句话 + 一个明确的下一步」。
// 现状的空态多是一行灰字（进展页右侧、素材库主区），既不引导也不体面；
// 统一走这里之后，七页的空态长得一样，且都给出可点的出路。

export interface EmptyStateProps {
  /** 图形（lucide 图标；统一 20px 常用尺寸） */
  icon?: ReactNode;
  title: string;
  /** 一句话说明——允许富文本（如内嵌 <code> 标出真实文件名） */
  description?: ReactNode;
  /** 下一步动作（按钮或链接）——空态没有出路时用户只能干瞪眼 */
  action?: ReactNode;
  /** 紧凑模式（嵌在小卡片里用，减少上下留白） */
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  compact = false,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-2 text-center",
        compact ? "py-6" : "py-10",
        className
      )}
    >
      {icon && (
        <div
          className="mb-1 flex h-11 w-11 items-center justify-center rounded-lg border border-border bg-surface-1 text-muted-foreground"
          aria-hidden="true"
        >
          {icon}
        </div>
      )}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && (
        <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
          {description}
        </p>
      )}
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
