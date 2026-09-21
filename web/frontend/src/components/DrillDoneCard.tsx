import { useTranslation } from "react-i18next";

import { BankCounts } from "./BankCounts";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

/**
 * 一轮走完的结束卡（2026-09-21 批次 C-2 从 ReviewQueue 拆出）：
 * 本轮**真正落盘**的写入数（取消 / 预览失败 / 冲突不计）+ 题库三态现状 + 重抽。
 * 拆出的直接理由：ReviewQueue 逼近 300 行预算，C-2 的题表与回退需要腾出空间。
 */
export function DrillDoneCard({
  graded,
  counts,
  busy,
  onRestart,
}: {
  graded: number;
  counts: Record<string, number>;
  busy: boolean;
  onRestart: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-1 p-4">
      <p className="text-sm font-medium text-foreground">{t("drill.done")}</p>
      <p className="text-xs text-muted-foreground">
        {t("drill.doneHint", { count: graded })}
      </p>
      {/* 题库现状（B-4）：练完看"会了"在涨——进度可见才有继续的动力 */}
      <BankCounts counts={counts} className="pt-1" />
      <div className="pt-1">
        <Button size="sm" onClick={onRestart} disabled={busy}>
          {t("drill.restart")}
        </Button>
      </div>
    </Card>
  );
}
