import * as React from "react";
import { cn } from "../../lib/utils";

// 数字原语（批 4；2026-09-17 实测反馈批按「克制专业」方向重做）：
//
// 规则（一处定义，全站遵守）——
// · **对齐靠 `tabular-nums`**（等宽数字特性：只统一前进宽度、保留字形边距，
//   位数变化不抖动，比等宽字体自然）；成列数字一律走 <Num>。
// · **数字字体统一走界面字体**——不再给数字单开等宽字体：两套字体（拉丁 UI +
//   等宽）的字宽 / x-height / 笔画粗细不同，摆在一起有"接缝感"（用户实测
//   「难看」的主因之一）。等宽字体留给代码 / 编号 / 日期（--font-mono 槽）。
// · **层级靠尺寸与文字深浅**，不靠色相；颜色只编码语义（如「已过期」红）。
// · 数字不用渐变、不用光斑——可读性优先，装饰与数据抢焦点（渐变两端还常
//   不达对比度要求）。
//
// <Num>：成列 / 变化中的数字（表格列、计数、金额、日期、百分比）。
// <StatValue>：KPI 主数字——rem 尺寸（随界面字号档缩放），单位降级做小、
// 基线对齐（约为主数字的 0.7 倍）。

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
  /** 单位 / 后缀（降级做小、次级色，与主数字基线对齐） */
  unit?: React.ReactNode;
}

export const StatValue = React.forwardRef<HTMLSpanElement, StatValueProps>(
  ({ className, value, unit, ...props }, ref) => (
    <span ref={ref} className={cn("flex items-baseline gap-1", className)} {...props}>
      <span
        className={cn(
          // text-3xl = 1.875rem ≈ 30px，且**随界面字号档等比缩放**（此前写死
          // 30px 不随档位走）；字距 0——等宽数字叠加负字距会"忽松忽紧"，
          // 正是"大数字毛躁"的来源；行高 1.1（leading-none 会让数字贴上下文）
          "text-3xl font-semibold leading-[1.1] tabular-nums"
        )}
      >
        {value}
      </span>
      {unit != null && (
        <span className="text-xl font-medium text-muted-foreground">{unit}</span>
      )}
    </span>
  )
);
StatValue.displayName = "StatValue";
