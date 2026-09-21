import { cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Num } from "./ui/number";

// 状态三态：值就是工作区里的真实取值，不翻译（与列表徽章 / 筛选器同一套约定）
// ——动它等于给数据改名（CSV 里的列值与判定都读它）。
const ORDER = ["未看", "看过", "会了"] as const;
const VARIANT: Record<string, "secondary" | "default" | "success"> = {
  未看: "secondary",
  看过: "default",
  会了: "success",
};

/**
 * 题库三态计数（2026-09-21 批次 B-4）：题库头部与训练结束卡共用——
 * 「未看 / 看过 / 会了」的分布一眼可见（此前 counts 后端已算、前端零消费，
 * 练了半天看不到"会了"在涨）。
 *
 * 只显示**有值的档**：counts 来自当前筛选范围，某档为 0 时摆一个空徽章
 * 反而像出了错。全为 0 时整块不渲染。
 */
export function BankCounts({
  counts,
  className,
}: {
  counts: Record<string, number>;
  className?: string;
}) {
  const shown = ORDER.filter((key) => (counts[key] ?? 0) > 0);
  if (!shown.length) return null;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1.5", className)}>
      {shown.map((key) => (
        <Badge key={key} variant={VARIANT[key]} className="rounded px-1.5 py-0.5 text-[11px]">
          {key}
          <Num className="text-[11px]">{counts[key]}</Num>
        </Badge>
      ))}
    </span>
  );
}
