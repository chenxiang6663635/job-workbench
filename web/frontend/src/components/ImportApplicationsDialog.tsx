import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle2, Clock, FileUp, Loader2, X } from "lucide-react";
import {
  api,
  type ImportPreviewResult,
  type ImportRowIssue,
} from "../api";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Textarea } from "./ui/input";
import { ErrorBanner } from "./ErrorBanner";
import type { TranslationKey } from "../i18n/locales/zh-CN";

interface Props {
  onClose: () => void;
  onImported: () => void;
}

// 预览表里值得展示的列（其余字段用户可在导入后于表内编辑）。
// **key 是 CSV 列名（取值，不翻），labelKey 是列头（展示，翻）**。
const PREVIEW_COLS: { key: string; labelKey: TranslationKey }[] = [
  { key: "公司", labelKey: "impCsv.colCompany" },
  { key: "岗位", labelKey: "impCsv.colRole" },
  { key: "方向", labelKey: "impCsv.colDirection" },
  { key: "批次", labelKey: "impCsv.colBatch" },
  { key: "当前阶段", labelKey: "impCsv.colStage" },
  { key: "截止日期", labelKey: "impCsv.colDeadline" },
  { key: "评分", labelKey: "impCsv.colScore" },
];

// 差异分色：新增绿 / 重复琥珀 / 错误红——颜色即结论，理由在最后一列。
// status 是后端给的取值（不翻），labelKey 是展示（翻）。
const STATUS_META: Record<
  string,
  { labelKey: TranslationKey; variant: "success" | "warning" | "destructive"; icon: typeof CheckCircle2 }
> = {
  ok: { labelKey: "impCsv.statusOk", variant: "success", icon: CheckCircle2 },
  duplicate: { labelKey: "impCsv.statusDuplicate", variant: "warning", icon: Clock },
  error: { labelKey: "impCsv.statusError", variant: "destructive", icon: AlertTriangle },
};

function RowBlock({ status, items }: { status: string; items: ImportRowIssue[] }) {
  const { t } = useTranslation();
  if (items.length === 0) return null;
  const meta = STATUS_META[status];
  const Icon = meta.icon;
  return (
    <div className="space-y-1.5">
      {items.map((it) => (
        <div
          key={it.line}
          className="flex items-start gap-2 rounded-lg border border-border bg-background/60 px-3 py-2"
        >
          <Badge
            variant={meta.variant}
            className="mt-0.5 shrink-0 gap-1 rounded px-1.5 py-0.5 text-[10px]"
          >
            <Icon size={10} /> {t(meta.labelKey)}
          </Badge>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-foreground">
              {PREVIEW_COLS.map(({ key, labelKey }) => {
                const v = (it.row[key] || "").trim();
                if (!v) return null;
                return (
                  <span key={key}>
                    <span className="text-muted-foreground">{t(labelKey)}</span> {v}
                  </span>
                );
              })}
            </div>
            {it.errors.length > 0 && (
              <p className="mt-1 text-[11px] leading-relaxed text-destructive">
                {t("impCsv.rowError", {
                  line: it.line,
                  errors: it.errors.join("；"),
                })}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 预览结论：计数徽章 + 按状态分组逐行说明 */
function PreviewReport({ preview }: { preview: ImportPreviewResult }) {
  const { t } = useTranslation();
  const total = preview.counts.ok + preview.counts.duplicate + preview.counts.error;
  return (
    <div className="space-y-3">
      {preview.unknown.length > 0 && (
        <p className="text-xs text-warning">
          {t("impCsv.unknown", { cols: preview.unknown.join("、") })}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Badge variant="success">{t("impCsv.willAdd", { count: preview.counts.ok })}</Badge>
        <Badge variant="warning">{t("impCsv.dupSkip", { count: preview.counts.duplicate })}</Badge>
        <Badge variant="destructive">{t("impCsv.errors", { count: preview.counts.error })}</Badge>
      </div>
      {total === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          {t("impCsv.empty")}
        </p>
      ) : (
        <div className="space-y-4">
          <RowBlock status="error" items={preview.error} />
          <RowBlock status="duplicate" items={preview.duplicate} />
          <RowBlock status="ok" items={preview.ok} />
        </div>
      )}
    </div>
  );
}

export default function ImportApplicationsDialog({ onClose, onImported }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [fileName, setFileName] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const readFile = (f: File | null) => {
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      setText(String(reader.result || ""));
      setFileName(f.name);
      setPreview(null);
      setError(null);
    };
    reader.onerror = () => setError(t("impCsv.readFailed"));
    reader.readAsText(f, "utf-8");
  };

  const runPreview = () => {
    if (!text.trim()) {
      setError(t("impCsv.pasteRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    api
      .importApplications(text, "preview")
      .then((r) => setPreview(r as ImportPreviewResult))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const commit = () => {
    if (!preview || preview.counts.error > 0) return;
    setBusy(true);
    setError(null);
    api
      .importApplications(text, "commit")
      .then(() => {
        // written 必然 ≥1：canCommit 已保证存在 ok 行且无错误行
        onImported();
        onClose();
      })
      .catch((e: Error) => {
        setError(e.message);
        setBusy(false);
      });
  };

  const canCommit = !!preview && preview.counts.error === 0 && preview.counts.ok > 0;

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[88vh] w-full max-w-4xl flex-col gap-0 rounded-2xl p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <FileUp size={16} className="text-primary" /> {t("impCsv.title")}
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <DialogDescription className="text-sm">
            {t("impCsv.desc")}
            <span className="text-muted-foreground">{t("impCsv.descNote")}</span>
          </DialogDescription>

          <div className="flex items-start gap-3">
            <Textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setPreview(null);
              }}
              rows={6}
              spellCheck={false}
              placeholder={t("impCsv.placeholder")}
              className="flex-1 resize-y font-mono text-[12px]"
            />
            <div className="flex flex-col gap-2">
              <input
                type="file"
                ref={fileRef}
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => readFile(e.target.files?.[0] || null)}
              />
              <Button variant="outline" className="border-dashed" onClick={() => fileRef.current?.click()}>
                <FileUp size={14} /> {t("impCsv.chooseFile")}
              </Button>
              <Button onClick={runPreview} disabled={busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                {t("impCsv.preview")}
              </Button>
            </div>
          </div>

          {fileName && (
            <p className="text-xs text-muted-foreground">
              {t("impCsv.loaded", { name: fileName })}
            </p>
          )}

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {preview && <PreviewReport preview={preview} />}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {preview
              ? canCommit
                ? t("impCsv.footerCommit", { count: preview.counts.ok })
                : t("impCsv.footerBlocked")
              : t("impCsv.footerNeedPreview")}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={commit}
              disabled={!canCommit || busy}
              title={canCommit ? "" : t("impCsv.commitBlockedTitle")}
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              {t("impCsv.confirm")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
