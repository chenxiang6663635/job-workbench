import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";

import { api } from "../api";
import { BankPreviewCard } from "./BankPreviewCard";
import { Button } from "./ui/button";
import { ErrorBanner } from "./ErrorBanner";

/**
 * 「从 03_面试准备 导入」的入口：预览 → 确认的两段式，自包含（2026-09-21 批次 B-1）。
 *
 * 从 `QuestionBank.tsx` 拆出的理由：那是 373 行的水位文件（只许变小），而本批要给
 * 工具栏再添「新增题目」入口——把导入这条完整的路整体搬出来腾空间，比在原地增删好。
 * 第二步仍走全站唯一的 `api.applyApproval`，与命令行 / MCP 同源。
 *
 * 预览卡与错误条用 `basis-full` 强制换到工具栏下一行：调用方是 flex-wrap 容器，
 * 本组件同时管两处渲染（按钮在行内、卡片另起一行）。
 */
export function BankImportButton({ onImported }: { onImported: () => void }) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<{ token: string; summary: string; diff: string[] } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onPreview = () => {
    setError(null);
    setBusy(true);
    api
      .previewQuestionImport()
      .then((r) => setPreview({ token: r.token, summary: r.summary, diff: r.diff }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onConfirm = () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    api
      .applyApproval(preview.token)
      .then(() => {
        setPreview(null);
        onImported();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <Button variant="outline" size="sm" onClick={onPreview} disabled={busy}>
        <Download size={13} className="mr-1" />
        {busy ? t("bank.importing") : t("bank.import")}
      </Button>
      {error && (
        <div className="basis-full">
          <ErrorBanner message={error} onClose={() => setError(null)} />
        </div>
      )}
      {preview && (
        <div className="basis-full">
          <BankPreviewCard
            summary={preview.summary}
            diff={preview.diff}
            busy={busy}
            confirmLabel={t("bank.confirmImport")}
            onConfirm={onConfirm}
            onCancel={() => setPreview(null)}
          />
        </div>
      )}
    </>
  );
}
