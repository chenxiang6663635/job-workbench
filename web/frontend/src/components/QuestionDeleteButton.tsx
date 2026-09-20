import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { previewQuestionDelete, type BankPreview } from "../lib/bank";
import { Button } from "./ui/button";
import { ErrorBanner } from "./ErrorBanner";
import { BankPreviewCard } from "./BankPreviewCard";

/**
 * 删单题（2026-09-20：给"导入"装刹车）。
 *
 * 为什么单独成组件：`QuestionDetailDialog.tsx` 已经 255 行、逼近 300 行的规模预算，
 * 再塞一段删除状态机会把它顶过线；拆出来也是本仓既有做法（行组件
 * `QuestionBankRow.tsx` 就是这么从 `QuestionBank.tsx` 拆走的）。
 *
 * 形态与改题一致：**先预览差异 → 用户确认 → 凭令牌落盘**，不提供"直接删"的口子。
 */
export function QuestionDeleteButton({
  id,
  onDeleted,
}: {
  id: string;
  onDeleted: () => void;
}) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<BankPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onPreview = () => {
    setBusy(true);
    setError(null);
    previewQuestionDelete(id)
      .then((r) => setPreview(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onConfirm = () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    // 两段式第二步：凭令牌落盘（与命令行 / MCP 同源；过期与冲突由服务端拒绝）
    api
      .applyApproval(preview.token)
      .then(() => onDeleted())
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <section className="mt-4 space-y-2 border-t border-border pt-4">
      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
      {preview ? (
        <BankPreviewCard
          summary={preview.summary}
          diff={preview.diff}
          busy={busy}
          confirmLabel={t("bank.confirmDelete")}
          onConfirm={onConfirm}
          onCancel={() => setPreview(null)}
        />
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onPreview} disabled={busy}>
            {busy ? t("bank.deletePreviewing") : t("bank.delete")}
          </Button>
          <span className="text-xs text-muted-foreground">{t("bank.deleteHint")}</span>
        </div>
      )}
    </section>
  );
}
