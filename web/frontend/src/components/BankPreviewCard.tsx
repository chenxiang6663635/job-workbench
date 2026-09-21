import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { parseImportDiff, type BankDiffKind } from "../lib/bankDiff";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

/**
 * 第一步的产物：差异表 + 确认 / 取消——**导入与删除共用同一套手感**。
 *
 * 用户是照着这张表决定要不要落盘的，所以两处的措辞与按钮位置必须一致；
 * 差别只在"确认"那个按钮的文案（写入 / 删除）由 `confirmLabel` 传进来。
 *
 * 2026-09-21（批次 C-3）：导入预览的差异表**能确定性解析**时渲染成真实表格 +
 * 状态徽章（新增 / 已存在 / 跳过 / 提示）——哪几行会真落盘一眼可见；其余形态
 * （新增 / 更新 / 删除的字段表）仍原样等宽展示，不做二次解析（解析错了比
 * 显示得丑危险得多——见 lib/bankDiff.ts 的解析条件）。
 */

// 徽章颜色与文案：分类来自 lib/bankDiff（末列是领域层生成的数据值，不是界面文案）
const KIND_VARIANT: Record<BankDiffKind, "success" | "warning" | "destructive" | "outline"> = {
  add: "success",
  dup: "warning",
  skip: "destructive",
  hint: "outline",
};
const KIND_LABEL: Record<BankDiffKind, string> = {
  add: "bank.diffAdd",
  dup: "bank.diffDup",
  skip: "bank.diffSkip",
  hint: "bank.diffHint",
};

export function BankPreviewCard({
  summary,
  diff,
  busy,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  summary: string;
  diff: string[];
  busy: boolean;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const table = useMemo(() => parseImportDiff(diff), [diff]);
  return (
    <Card className="space-y-2 p-3">
      <p className="text-sm font-medium text-foreground">{summary}</p>
      {table ? (
        <div className="max-h-48 overflow-auto rounded-lg border border-border bg-surface-0">
          <table className="w-full border-collapse text-[11px] leading-relaxed">
            <thead>
              <tr className="border-b border-border text-left text-muted-foreground">
                {table.header.map((cell) => (
                  <th key={cell} scope="col" className="px-2 py-1 font-medium">
                    {cell}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, index) => (
                <tr key={index} className="border-b border-border/60 last:border-0">
                  {row.cells.slice(0, 3).map((cell, cellIndex) => (
                    <td key={cellIndex} className="px-2 py-1 align-top text-foreground">
                      {cell}
                    </td>
                  ))}
                  <td className="px-2 py-1 align-top">
                    {/* 徽章给分类色标、原文照旧显示（截断 + title 悬停看全）——
                        跳过原因 / 来源文件这些细节不能被色标吞掉 */}
                    <span className="flex items-center gap-1.5">
                      <Badge
                        variant={KIND_VARIANT[row.kind]}
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px]"
                      >
                        {t(KIND_LABEL[row.kind])}
                      </Badge>
                      <span className="truncate text-muted-foreground" title={row.cells[3]}>
                        {row.cells[3]}
                      </span>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* 解析不了就原样等宽展示（不做二次解析——用户据此决定要不要落盘） */
        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {diff.join("\n")}
        </pre>
      )}
      <div className="flex gap-2">
        <Button size="sm" onClick={onConfirm} disabled={busy}>
          {busy ? t("bank.writing") : confirmLabel || t("bank.confirmWrite")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
      </div>
    </Card>
  );
}
