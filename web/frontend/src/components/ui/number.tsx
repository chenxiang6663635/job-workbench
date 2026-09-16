import * as React from "react";
import { cn } from "../../lib/utils";

// 数字原语（批 4）：全站数字的秩序感从这两个组件来——
// 现状是「tabular-nums 只有 4 处、其余数字位数一变就参差」，而数据产品的第一气质
// 就是数字成列时的整齐。约定：**任何会成列出现的数字都走 <Num>**。
//
// · <Num>：等宽数字（tabular-nums）+ 可选右对齐；表格列、金额、计数、日期都用它。
// · <StatValue>：KPI 主数字——30px、单位降级做小、基线对齐；渐变文字全站仅此一处
//   （Stripe 的渐变纪律：渐变不用于正文，数字是唯一被允许的例外）。

export interface NumProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** 等宽数字（默认开）：数字变化或成列时不抖动 */
  tabular?: boolean;
  /** 右对齐（表格数字列默认应右对齐，位宽不齐的列才需显式关闭） */
  align?: "left" | "right";
  /** 弱化为次级色（表格里的辅助数字） */
  muted?: boolean;
}

export const Num = React.forwardRef<HTMLSpanElement, NumProps>(
  ({ className, tabular = true, align = "left", muted = false, ...props }, ref) => (
    <span
      ref={ref}
      className={cn(
        "font-mono",
        tabular && "tabular-nums",
        align === "right" && "text-right",
        muted ? "text-muted-foreground" : "text-foreground",
        className
      )}
      {...props}
    />
  )
);
Num.displayName = "Num";

export interface StatValueProps extends React.HTMLAttributes<HTMLSpanElement> {
  value: React.ReactNode;
  /** 单位 / 后缀 / 比较值（降级做小、次级色，与主数字基线对齐） */
  unit?: React.ReactNode;
  /** 主数字渐变（仅 KPI 卡主数字启用；默认关闭，正文数字禁止渐变） */
  gradient?: boolean;
}

export const StatValue = React.forwardRef<HTMLSpanElement, StatValueProps>(
  ({ className, value, unit, gradient = false, ...props }, ref) => (
    <span ref={ref} className={cn("flex items-baseline gap-1", className)} {...props}>
      <span
        className={cn(
          // KPI 数字跟随**界面字体**（Inter/系统）而不是等宽栈——用户实测 mono 大数字
          // 与整页观感脱节（「字体还没有设置」的体感来源）；tabular-nums 保留：
          // 位数变化不抖动、四卡并排基线一致。渐变仅显式传 gradient 才启用。
          "text-[30px] font-semibold leading-none tracking-tight tabular-nums",
          gradient
            ? "bg-gradient-to-b from-foreground to-primary/70 bg-clip-text text-transparent"
            : "text-foreground"
        )}
      >
        {value}
      </span>
      {unit != null && (
        <span className="text-xs font-medium text-muted-foreground">{unit}</span>
      )}
    </span>
  )
);
StatValue.displayName = "StatValue";
