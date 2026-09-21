// 记录删除按钮（批 D 数据安全网）：泛型版——行内小按钮 → 预览请求 →
// 确认弹窗 → 凭令牌落盘。
//
// 与 QuestionDeleteButton（内联预览卡）的差别：那个住在详情弹窗里、有整块空间；
// 这个是**行内**按钮，预览差异只能进弹窗。两者同一纪律：先预览、后确认，
// 落盘一律走 `api.applyApproval`（写通道全站只有一条，不提供"直接删"的口子）。
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { api } from "../api";
import type { RecordPreview } from "../lib/records";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { ErrorBanner } from "./ErrorBanner";

export default function DeleteRecordButton({
  preview,
  onDeleted,
  titleKey = "records.deleteTitle",
}: {
  /** 预览请求（各域传入自己的 preview 函数） */
  preview: () => Promise<RecordPreview>;
  /** 落盘成功后的回调（列表重拉） */
  onDeleted: () => void;
  /** 弹窗标题 / 按钮提示的文案键（默认通用「删除记录」） */
  titleKey?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<RecordPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const close = () => {
    setOpen(false);
    setData(null);
  };

  const onPreview = () => {
    setOpen(true);
    setData(null);
    setError(null);
    setBusy(true);
    preview()
      .then((r) => setData(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onConfirm = () => {
    if (!data) return;
    setBusy(true);
    setError(null);
    // 两段式第二步：凭令牌落盘（与命令行 / MCP 同源；过期与冲突由服务端拒绝）
    api
      .applyApproval(data.token)
      .then(() => {
        close();
        onDeleted();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <Button
        variant="ghost"
        size="icon"
        className="h-7 w-7 text-muted-foreground"
        title={t(titleKey)}
        aria-label={t(titleKey)}
        onClick={onPreview}
      >
        <Trash2 size={13} />
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          // 落盘 / 预览请求在飞时不可关（Esc / 遮罩同款）
          if (!next && !busy) close();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(titleKey)}</DialogTitle>
            <DialogDescription>{t("records.deleteHint")}</DialogDescription>
          </DialogHeader>
          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
          {data ? (
            <div className="space-y-2">
              <p className="break-words text-sm font-medium text-foreground">
                {data.summary}
              </p>
              {/* diff 原样等宽展示（与 NotesToggleDialog 同款）：解析错了比
                  显示得丑危险得多（用户据此决定要不要落盘） */}
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {data.diff.join("\n")}
              </pre>
            </div>
          ) : (
            busy && (
              <p className="text-xs text-muted-foreground">{t("records.previewing")}</p>
            )
          )}
          <DialogFooter>
            <Button onClick={onConfirm} disabled={busy || !data}>
              {busy && data ? t("records.deleting") : t("records.deleteConfirm")}
            </Button>
            <Button variant="ghost" onClick={close} disabled={busy}>
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
