import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

// 页头原语（批 4）：七页此前各写各的标题区（有的 text-lg 有的 text-2xl、
// 描述有无不一、右侧动作位各按各的排）。统一到这一个组件后，页面切换时
// 标题的基线、字号、间距完全一致——「同一套产品」的第一眼观感由它兜底。

export interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** 右侧动作区（按钮、筛选器等）——窄屏自动换行到标题下方 */
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({ title, description, actions, className }: PageHeaderProps) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-start justify-between gap-3",
        className
      )}
    >
      <div className="min-w-0">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
