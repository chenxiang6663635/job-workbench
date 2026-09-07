import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Clock, FileUp, Loader2, X } from "lucide-react";
import {
  api,
  type ImportPreviewResult,
  type ImportRowIssue,
} from "../api";

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
const STATUS_META: Record<string, { label: string; badge: string; icon: typeof CheckCircle2 }> = {
  ok: { label: "新增", badge: "bg-good/15 text-good", icon: CheckCircle2 },
  duplicate: { label: "重复", badge: "bg-warn/15 text-warn", icon: Clock },
  error: { label: "错误", badge: "bg-bad/15 text-bad", icon: AlertTriangle },
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
          className="flex items-start gap-2 rounded-lg border border-white/5 bg-ink-950/60 px-3 py-2"
        >
          <span
            className={`mt-0.5 inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${meta.badge}`}
          >
            <Icon size={10} /> {meta.label}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-200">
              {PREVIEW_COLS.map(({ key, label }) => {
                const v = (it.row[key] || "").trim();
                if (!v) return null;
                return (
                  <span key={key}>
                    <span className="text-slate-500">{label}</span> {v}
                  </span>
                );
              })}
            </div>
            {it.errors.length > 0 && (
              <p className="mt-1 text-[11px] leading-relaxed text-bad">
                第 {it.line} 行：{it.errors.join("；")}
              </p>
            )}
          </div>
        </div>
      ))}
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="flex h-[88vh] w-full max-w-4xl flex-col rounded-2xl border border-white/10 bg-ink-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-100">
            <FileUp size={16} className="text-accent" /> 批量导入投递记录（CSV）
          </div>
          <button onClick={onClose} className="cursor-pointer text-slate-400 hover:text-slate-200">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <p className="text-sm text-slate-400">
            粘贴或上传 CSV（Excel「另存为 CSV UTF-8」即可）。表头与追踪表字段同名，
            允许缺列（缺的留空）、未知列忽略。
            <span className="text-slate-500">
              预览确认后才会写入，重复与错误行会标色说明原因。
            </span>
          </p>

          <div className="flex items-start gap-3">
            <textarea
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setPreview(null);
              }}
              rows={6}
              spellCheck={false}
              placeholder={"公司,岗位,方向,批次,当前阶段,截止日期,评分\n某某科技,热管理工程师,hvac,正式批,待投,2026-09-30,72"}
              className="flex-1 rounded-lg border border-white/10 bg-ink-900 px-3 py-2 font-mono text-[12px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-accent/60"
            />
            <div className="flex flex-col gap-2">
              <input
                type="file"
                ref={fileRef}
                accept=".csv,text/csv"
                className="hidden"
                onChange={(e) => readFile(e.target.files?.[0] || null)}
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg border border-dashed border-white/20 px-3 py-2 text-sm text-slate-300 transition-colors hover:border-accent/50 hover:text-accent"
              >
                <FileUp size={14} /> 选择 CSV 文件
              </button>
              <button
                onClick={runPreview}
                disabled={busy}
                className="flex cursor-pointer items-center gap-1.5 whitespace-nowrap rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft disabled:opacity-40"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                预览校验
              </button>
            </div>
          </div>
          {fileName && <p className="text-xs text-slate-500">已载入文件：{fileName}</p>}

          {error && (
            <div className="flex items-center gap-2 rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
              <AlertTriangle size={14} /> {error}
            </div>
          )}

          {preview && (
            <div className="space-y-3">
              {preview.unknown.length > 0 && (
                <p className="text-xs text-warn">
                  忽略未知列：{preview.unknown.join("、")}
                </p>
              )}
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-good/15 px-2.5 py-1 text-good">
                  将新增 {preview.counts.ok} 条
                </span>
                <span className="rounded-full bg-warn/15 px-2.5 py-1 text-warn">
                  重复跳过 {preview.counts.duplicate} 条
                </span>
                <span className="rounded-full bg-bad/15 px-2.5 py-1 text-bad">
                  错误 {preview.counts.error} 条
                </span>
              </div>
              {preview.counts.ok + preview.counts.duplicate + preview.counts.error === 0 ? (
                <p className="rounded-xl border border-dashed border-white/15 px-4 py-6 text-center text-sm text-slate-500">
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
          )}
        </div>

        <div className="flex items-center justify-between border-t border-white/10 px-5 py-3">
          <p className="text-xs text-slate-500">
            {preview
              ? canCommit
                ? `确认后将新增 ${preview.counts.ok} 条，并逐条记入变更时间线`
                : "存在错误行时不能提交"
              : "先预览校验，确认差异后再写入"}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
            >
              取消
            </button>
            <button
              onClick={commit}
              disabled={!canCommit || busy}
              title={canCommit ? "" : "有错误行或没有可新增的行"}
              className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              确认导入
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
