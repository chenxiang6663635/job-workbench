import * as React from "react";
import { cn } from "../../lib/utils";

// 数字原语（批 4；2026-09-17 实测反馈批重做；批 4.6 接入数字槽与字重阶梯）：
//
// 规则（一处定义，全站遵守）——
// · **字体走数字槽**（`font-numeric` → --font-numeric-stack，默认 Geist Mono）：
//   数值统一由设置页「数字字体」决定，与界面字体解耦；等宽字体留给代码 /
//   编号 / 日期时间（--font-mono 槽）。"follow" 档 = 跟随界面字体（退回
//   tabular-nums 对齐，方向 A 行为）；正文内联数字可 `numeric={false}` 退出。
// · **对齐靠 `tabular-nums`**（等宽数字特性：只统一前进宽度、保留字形边距，
//   位数变化不抖动，比等宽字体自然）；成列数字一律走 <Num>。
// · **字重阶梯**：KPI 主数字 600 + 字距 -0.02em（大字号轻微收紧；忌 700+——
//   深色底上会糊）；列表 / 行内数值 500（比正文实一档，"数据感"的来源）。
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
  /** 走数字槽（默认开）；正文内联数字 / 需跟随界面字体处显式关闭 */
  numeric?: boolean;
}

export const Num = React.forwardRef<HTMLSpanElement, NumProps>(
  (
    { className, tabular = true, align = "left", muted = false, numeric = true, ...props },
    ref
  ) => (
    <span
      ref={ref}
      className={cn(
        // 数字阶梯基准：500 字重（列表 / 行内数值）——调用方可用 font-* 类
        // 覆盖（cn 走 twMerge，后写的类胜出）
        "font-medium",
        numeric && "font-numeric",
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
          // text-3xl = 1.875rem ≈ 30px，且**随界面字号档等比缩放**；KPI 阶梯 =
          // 数字槽 + 600 字重 + 字距 -0.02em（大字号轻微收紧——此前因"负字距
          // 让大数字毛躁"取 0，实测那来自更激进的 -0.05em+ 与比例数字；
          // tabular 宽度统一，-0.02em 只让大字号更紧致）；行高 1.1
          "font-numeric text-3xl font-semibold leading-[1.1] tracking-[-0.02em] tabular-nums"
        )}
      >
        {value}
      </span>
      {unit != null && (
        <span className="font-numeric text-xl font-medium text-muted-foreground">
          {unit}
        </span>
      )}
    </span>
  )
);
StatValue.displayName = "StatValue";
