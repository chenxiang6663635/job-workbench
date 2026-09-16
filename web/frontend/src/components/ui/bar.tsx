import { cn } from "../../lib/utils";

// 水平条原语（批 4）：此前漏斗、复盘转化率、失败聚类、维度得分是**四份互不复用的
// 纯 div 宽度条**——轨道高（h-3.5 / h-1.5）、圆角、过渡（无 / 500 / 700）各不相同，
// 视觉上「同一页里的进度条不是一个东西」。统一到这一个组件，颜色一律由调用方给
// 语义色（chart token 或 CSS 变量），原语自己不带任何硬编码色。

export interface BarProps {
  /** 0..1 的进度；超界自动夹取 */
  value: number;
  /** CSS 颜色（默认 hsl(var(--primary))） */
  color?: string;
  /** 轨道高度：sm 用于行内小条（h-1.5）、md 用于漏斗级（h-3.5） */
  height?: "sm" | "md";
  /** 是否画轨道底（默认画；个别场景只要填充时关掉） */
  track?: boolean;
  /** 最小可见宽度（百分点，默认 3）——0 值也保留一丝视觉存在，
      避免「有这一行但完全看不到」被误读为数据缺失 */
  minPercent?: number;
  className?: string;
}

export function Bar({
  value,
  color,
  height = "md",
  track = true,
  minPercent = 3,
  className,
}: BarProps) {
  const safe = Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0;
  const percent = safe === 0 ? 0 : Math.max(minPercent, Math.round(safe * 100));
  return (
    <div
      className={cn(
        "w-full overflow-hidden rounded-full",
        height === "sm" ? "h-1.5" : "h-3.5",
        track && "bg-secondary/40",
        className
      )}
      role="presentation"
    >
      <div
        className="h-full rounded-full transition-[width] duration-500 ease-premium"
        style={{ width: `${percent}%`, background: color || "hsl(var(--primary))" }}
      />
    </div>
  );
}
