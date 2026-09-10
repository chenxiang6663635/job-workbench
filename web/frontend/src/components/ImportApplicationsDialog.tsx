import { useRef, useState } from "react";
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
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Textarea } from "./ui/input";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  onClose: () => void;
  onImported: () => void;
}

// 预览表里值得展示的列（其余字段用户可在导入后于表内编辑）
const PREVIEW_COLS: { key: string; label: string }[] = [
  { key: "公司", label: "公司" },
  { key: "岗位", label: "岗位" },
  { key: "方向", label: "方向" },
  { key: "批次", label: "批次" },
  { key: "当前阶段", label: "阶段" },
  { key: "截止日期", label: "截止" },
  { key: "评分", label: "评分" },
];

// 差异分色：新增绿 / 重复琥珀 / 错误红——颜色即结论，理由在最后一列
const STATUS_META: Record<
  string,
  { label: string; variant: "success" | "warning" | "destructive"; icon: typeof CheckCircle2 }
> = {
  ok: { label: "新增", variant: "success", icon: CheckCircle2 },
  duplicate: { label: "重复", variant: "warning", icon: Clock },
  error: { label: "错误", variant: "destructive", icon: AlertTriangle },
};

function RowBlock({ status, items }: { status: string; items: ImportRowIssue[] }) {
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
            <Icon size={10} /> {meta.label}
          </Badge>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-foreground">
              {PREVIEW_COLS.map(({ key, label }) => {
                const v = (it.row[key] || "").trim();
                if (!v) return null;
                return (
                  <span key={key}>
                    <span className="text-muted-foreground">{label}</span> {v}
                  </span>
                );
              })}
            </div>
            {it.errors.length > 0 && (
              <p className="mt-1 text-[11px] leading-relaxed text-destructive">
                第 {it.line} 行：{it.errors.join("；")}
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
  const total = preview.counts.ok + preview.counts.duplicate + preview.counts.error;
  return (
    <div className="space-y-3">
      {preview.unknown.length > 0 && (
        <p className="text-xs text-warning">忽略未知列：{preview.unknown.join("、")}</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Badge variant="success">将新增 {preview.counts.ok} 条</Badge>
        <Badge variant="warning">重复跳过 {preview.counts.duplicate} 条</Badge>
        <Badge variant="destructive">错误 {preview.counts.error} 条</Badge>
      </div>
      {total === 0 ? (
        <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          没有识别到数据行，请检查 CSV 格式（表头 + 至少一行数据）。
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
    reader.onerror = () => setError("文件读取失败");
    reader.readAsText(f, "utf-8");
  };

  const runPreview = () => {
    if (!text.trim()) {
      setError("请先粘贴 CSV 内容或选择文件");
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
            <FileUp size={16} className="text-primary" /> 批量导入投递记录（CSV）
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-sm text-muted-foreground">
            粘贴或上传 CSV（Excel「另存为 CSV UTF-8」即可）。表头与追踪表字段同名，
            允许缺列（缺的留空）、未知列忽略。
            预览确认后才会写入，重复与错误行会标色说明原因。
          </p>

          <div className="flex items-start gap-3">
            <Textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setPreview(null);
              }}
              rows={6}
              spellCheck={false}
              placeholder={"公司,岗位,方向,批次,当前阶段,截止日期,评分\n某某科技,热管理工程师,hvac,正式批,待投,2026-09-30,72"}
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
                <FileUp size={14} /> 选择 CSV 文件
              </Button>
              <Button onClick={runPreview} disabled={busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                预览校验
              </Button>
            </div>
          </div>

          {fileName && <p className="text-xs text-muted-foreground">已载入文件：{fileName}</p>}

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {preview && <PreviewReport preview={preview} />}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {preview
              ? canCommit
                ? `确认后将新增 ${preview.counts.ok} 条，并逐条记入变更时间线`
                : "存在错误行时不能提交"
              : "先预览校验，确认差异后再写入"}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button
              onClick={commit}
              disabled={!canCommit || busy}
              title={canCommit ? "" : "有错误行或没有可新增的行"}
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              确认导入
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
