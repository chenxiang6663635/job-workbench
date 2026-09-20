import { useTranslation } from "react-i18next";
import { Button } from "./ui/button";
import { Card } from "./ui/card";

/**
 * 第一步的产物：差异表 + 确认 / 取消——**导入与删除共用同一套手感**。
 *
 * 用户是照着这张表决定要不要落盘的，所以两处的措辞与按钮位置必须一致；
 * 差别只在"确认"那个按钮的文案（写入 / 删除）由 `confirmLabel` 传进来。
 */
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
  return (
    <Card className="space-y-2 p-3">
      <p className="text-sm font-medium text-foreground">{summary}</p>
      {/* diff 是后端给的 Markdown 表格文本：原样等宽展示，不做二次解析——
          解析错了比显示得丑危险得多（用户据此决定要不要落盘） */}
      <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
        {diff.join("\n")}
      </pre>
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
