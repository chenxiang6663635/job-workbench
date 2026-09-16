import * as React from "react";
import { cn } from "../../lib/utils";

/**
 * 单选分段控件（radio group）。
 *
 * **为什么不用 `ui/tabs`**：Tabs 是"标签页"语义——触发器上带 `aria-controls`，
 * 指向一个内容面板。把排序 / 编辑模式这种"单选开关"塞进 Tabs，就会给触发器挂上
 * 一个**不存在的** content id（axe 的 `aria-valid-attr-value` 会报，2026-09-13 的
 * 两条豁免就是它）。根治办法就是换成真正的单选控件。
 *
 * **为什么用原生 radio 而不是再造一个按钮组**：`role="radiogroup"` + 原生
 * `input[type=radio]` 让方向键切换、分组语义、"选中"状态全部由浏览器给出，
 * 不需要自己实现 roving tabindex，也不用新增依赖（Radix 的 toggle-group 没装）。
 * 焦点环画在可见的 label 上——input 本身是 `sr-only` 的，环画它身上看不见。
 *
 * 视觉沿用 `ui/tabs` 的选中样式（渐变底 + primary 文字 + 发光），避免出现第二套
 * 视觉语言。
 */
export interface SegmentedOption<T extends string> {
  value: T;
  /** 已翻译的文本（组件自身不查语言包：与 FormField 的 label 同一约定） */
  label: string;
  icon?: React.ReactNode;
}

interface SegmentedProps<T extends string> {
  value: T;
  options: SegmentedOption<T>[];
  onChange: (value: T) => void;
  /** 这一组单选的**名字**（屏幕阅读器读它）。必填——没有它读出来就是"一组无名单选" */
  ariaLabel: string;
  className?: string;
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: SegmentedProps<T>) {
  // 同页可能有第二组分段控件；同名 radio 会被浏览器当成同一组，必须逐实例区分
  const name = React.useId();

  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={cn(
        "inline-flex flex-wrap items-center gap-1 rounded-lg border border-border bg-secondary/40 p-1",
        className
      )}
    >
      {options.map((option) => {
        const checked = option.value === value;
        return (
          <label
            key={option.value}
            className={cn(
              // [&_svg]:shrink-0：窄屏/长标签下图标曾被 flex 压扁（#5 与 tabs 同款保险）
              "relative inline-flex cursor-pointer items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-all duration-200 ease-premium [&_svg]:shrink-0",
              checked
                ? // 激活态文字用前景色（独立审查 MAJOR：浅色下 primary 对
                  // primary/20 渐变底只有 ~4.0:1）——激活由底色 + 发光承担
                  "bg-gradient-to-b from-primary/20 to-primary/10 text-foreground shadow-glow-primary"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={checked}
              onChange={() => onChange(option.value)}
              className="peer sr-only"
            />
            {option.icon}
            {option.label}
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-0 rounded-md peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
            />
          </label>
        );
      })}
    </div>
  );
}
