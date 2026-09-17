import * as React from "react";
import { cn } from "../../lib/utils";
import { Bar } from "./bar";
import { Num } from "./number";

// 排名条原语（批 4.6）：名称 + 归一化条 + 右对齐数值——把「裸计数列表」
// 升级成可直接比较的读数（Tremor BarList 的形制：默认降序、默认不动画）。
// 与「投递漏斗」同一套行形制（名称 / 条 / 右对齐数字），全页只有一种读数方式。
//
// 参数口径（调研 B，2026-09-17）——
// · 条长按 max 归一化（默认取当前列表最大值）；0 值保留最小可见宽度
//   （ui/bar.tsx 的 minPercent），避免"有这一行但看不见"被误读为缺数据；
// · 颜色由调用方给语义色（原语不带硬编码色，同 ui/bar.tsx 约定）；
// · 默认降序 = 行序即名次；顺序有意义的列表（阶段漏斗）传 sortDesc={false}；
// · 行内数值走 <Num>（数字槽 + tabular + 500 字重），成列右对齐——全站
//   数字体系同源；数值用中性色，语义色只留给状态与涨跌；
// · 可点击行渲染为 <button>（drill 下钻），键盘可达；hover 转主色 + 箭头
//   浮现（与 ClickRow 的既有交互一致）。

export interface BarListItem {
  /** React key（label 同值场景用唯一 key） */
  key: string;
  /** 行名（已翻译文本；原语不查语言包） */
  label: React.ReactNode;
  value: number;
  /** 条色（CSS 颜色；缺省走 --primary） */
  color?: string;
  /** 行 title（悬停提示，如「阶段 X：N 个岗位」） */
  title?: string;
  /** 点击（给了就渲染成按钮行） */
  onClick?: () => void;
}

export interface BarListProps {
  items: BarListItem[];
  /** 归一化基准（默认 = 当前列表最大值；跨列表同基准时显式传） */
  max?: number;
  /** 降序（默认 true）；漏斗等顺序有意义的列表传 false */
  sortDesc?: boolean;
  /** 名称列宽（默认 w-20；与相邻块对齐时显式传同值） */
  labelWidth?: string;
  /** 数值列宽（默认 w-8） */
  valueWidth?: string;
  /** 条高（sm 行内小条 / md 主可视化，透传 ui/bar） */
  barHeight?: "sm" | "md";
  /** 行间距（默认 space-y-2.5，与投递漏斗同一节奏） */
  gapClassName?: string;
  ariaLabel?: string;
  className?: string;
}

export function BarList({
  items,
  max,
  sortDesc = true,
  labelWidth = "w-20",
  valueWidth = "w-8",
  barHeight = "sm",
  gapClassName = "space-y-2.5",
  ariaLabel,
  className,
}: BarListProps) {
  const rows = sortDesc ? [...items].sort((a, b) => b.value - a.value) : items;
  const peak = max ?? Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className={cn("list-none p-0", gapClassName, className)} aria-label={ariaLabel}>
      {rows.map((item) => {
        const body = (
          <>
            <span
              className={cn(
                labelWidth,
                "shrink-0 truncate text-muted-foreground transition-colors group-hover:text-primary"
              )}
              title={typeof item.label === "string" ? item.label : undefined}
            >
              {item.label}
            </span>
            <Bar
              value={item.value / peak}
              color={item.color}
              height={barHeight}
              className="flex-1"
            />
            <Num align="right" className={cn(valueWidth, "shrink-0")}>
              {item.value}
            </Num>
            {item.onClick && (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                className="shrink-0 text-muted-foreground opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100"
              >
                <path d="m9 18 6-6-6-6" />
              </svg>
            )}
          </>
        );
        const rowClass = "group flex w-full items-center gap-3 text-left text-xs rounded-md focus-visible:ring-2 focus-visible:ring-ring";
        return (
          <li key={item.key}>
            {item.onClick ? (
              <button
                type="button"
                onClick={item.onClick}
                title={item.title}
                className={cn(rowClass, "cursor-pointer")}
              >
                {body}
              </button>
            ) : (
              <div title={item.title} className={rowClass}>
                {body}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
