import { useTranslation } from "react-i18next";

import { tagsOf, WRONG_TAG } from "../lib/drill";
import { cn } from "../lib/utils";

/**
 * 本轮题表（2026-09-21 批次 C-2）：一排题号格——当前题高亮、**已落盘**的打勾、
 * 错题带红边；点任意格直接跳过去。
 *
 * 为什么要有它：抽题是只读的，而"已写"只增不减——误点自评写了错的状态，
 * 此前只有「下一题」一条路（错了只能重抽整轮，已写的那笔还留在题上）。
 * 现在点题表（或按 ←）回到那一题改回来即可；跳转一律收起答案（换了题还摊着
 * 上一个答案等于剧透，"盲答"这条纪律不能被回退路径破坏）。
 */
export function DrillRoundMap({
  items,
  index,
  written,
  onJump,
}: {
  items: { 标签?: string; 题目: string }[];
  index: number;
  written: Set<number>;
  onJump: (index: number) => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className="flex flex-wrap items-center gap-1"
      role="group"
      aria-label={t("drill.roundMap")}
    >
      {items.map((item, i) => {
        const isCurrent = i === index;
        const isWritten = written.has(i);
        const isWrong = tagsOf(item.标签 || "").includes(WRONG_TAG);
        return (
          <button
            key={`${i}-${item.题目}`}
            type="button"
            onClick={() => onJump(i)}
            aria-current={isCurrent ? "step" : undefined}
            title={item.题目}
            className={cn(
              "h-7 min-w-7 cursor-pointer rounded-md border px-1.5 font-numeric text-[11px] tabular-nums transition-colors",
              isWritten
                ? "border-success/60 bg-success/10 text-foreground"
                : "border-border text-muted-foreground hover:border-border-strong hover:text-foreground",
              isCurrent && "border-primary bg-primary/10 text-foreground ring-1 ring-primary/40",
              isWrong && !isCurrent && "border-destructive/60"
            )}
          >
            {isWritten ? "✓" : i + 1}
          </button>
        );
      })}
    </div>
  );
}
