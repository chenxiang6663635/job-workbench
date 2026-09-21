// 岗位改名弹窗（批 D 数据安全网）：表单（新公司 / 新岗位）→ 预览（目录名
// 旧 → 新 + JD 首行同步说明）→ 凭令牌落盘。
//
// 与 DeleteRecordButton 同一纪律：先预览、后确认，落盘一律走 `api.applyApproval`
// （写通道全站只有一条）。改名可逆（不做目录快照），但预览必须列清将动什么——
// "可逆"不是省略确认的理由。
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";

import { api } from "../api";
import { previewRenameJob, type RecordPreview } from "../lib/records";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { FormField } from "./FormField";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { ErrorBanner } from "./ErrorBanner";

/** 目录名 → (公司, 岗位)：与后端 `split_dir_name` 同口径（首个下划线、两端 trim）。 */
function splitDir(dir: string): [string, string] {
  const idx = dir.indexOf("_");
  if (idx < 0) return [dir.trim(), ""];
  return [dir.slice(0, idx).trim(), dir.slice(idx + 1).trim()];
}

export default function RenameJobDialog({
  dir,
  onRenamed,
}: {
  /** 当前岗位目录名 */
  dir: string;
  /** 改名成功后的回调（父级关详情 + 重拉列表） */
  onRenamed: () => void;
}) {
  const { t } = useTranslation();
  const [initialCompany, initialRole] = splitDir(dir);
  const [open, setOpen] = useState(false);
  const [company, setCompany] = useState(initialCompany);
  const [role, setRole] = useState(initialRole);
  const [data, setData] = useState<RecordPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const openDialog = () => {
    setCompany(initialCompany);
    setRole(initialRole);
    setData(null);
    setError(null);
    setOpen(true);
  };

  const close = () => {
    setOpen(false);
    setData(null);
  };

  const onPreview = () => {
    setBusy(true);
    setError(null);
    previewRenameJob(dir, company, role)
      .then((r) => setData(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onConfirm = () => {
    if (!data) return;
    setBusy(true);
    setError(null);
    api
      .applyApproval(data.token)
      .then(() => {
        close();
        onRenamed();
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
        title={t("jobs.renameTitle")}
        aria-label={t("jobs.renameTitle")}
        onClick={openDialog}
      >
        <Pencil size={13} />
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next && !busy) close();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("jobs.renameTitle")}</DialogTitle>
            <DialogDescription>{t("jobs.renameDesc")}</DialogDescription>
          </DialogHeader>
          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
          {data ? (
            <div className="space-y-2">
              <p className="break-words text-sm font-medium text-foreground">
                {data.summary}
              </p>
              {/* diff 原样等宽展示（与 DeleteRecordButton 同款）：解析错了比
                  显示得丑危险得多（用户据此决定要不要落盘） */}
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
                {data.diff.join("\n")}
              </pre>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <FormField label={t("jobs.renameCompany")}>
                <Input value={company} onChange={(e) => setCompany(e.target.value)} />
              </FormField>
              <FormField label={t("jobs.renameRole")}>
                <Input value={role} onChange={(e) => setRole(e.target.value)} />
              </FormField>
            </div>
          )}
          <DialogFooter>
            {data ? (
              <Button onClick={onConfirm} disabled={busy}>
                {busy ? t("jobs.renaming") : t("jobs.renameConfirm")}
              </Button>
            ) : (
              <Button onClick={onPreview} disabled={busy || !company.trim()}>
                {busy ? t("records.previewing") : t("jobs.renamePreview")}
              </Button>
            )}
            <Button variant="ghost" onClick={close} disabled={busy}>
              {t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
