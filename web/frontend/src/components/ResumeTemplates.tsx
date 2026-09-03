import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  FileCode2,
  FileText,
  FileImage,
  Loader2,
  Printer,
} from "lucide-react";
import {
  api,
  type ResumeBuildResult,
  type ResumeTemplateItem,
} from "../api";

// 从文件列表里挑出手写模板（resume_<版本>.html），供「生成 PDF」按钮使用
function templateVersion(rel: string): string | null {
  const m = /resume_([A-Za-z0-9_-]+)\.html$/.exec(rel);
  return m ? m[1] : null;
}

function fileIcon(item: ResumeTemplateItem) {
  if (item.kind === "text") return <FileCode2 size={15} className="text-accent" />;
  const ext = item.name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={15} className="text-bad" />;
  return <FileImage size={15} className="text-warn" />;
}

function fmtSize(n: number) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export default function ResumeTemplates() {
  const [items, setItems] = useState<ResumeTemplateItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ResumeTemplateItem | null>(null);
  const [textContent, setTextContent] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<ResumeBuildResult | null>(null);

  useEffect(() => {
    api
      .listResumeTemplates()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message));
  }, []);

  // 选中文件后：文本类拉内容，二进制直接用文件 URL
  useEffect(() => {
    if (!selected || selected.kind !== "text") {
      setTextContent(null);
      return;
    }
    api
      .resumeTemplateContent(selected.rel)
      .then((r) => setTextContent(r.type === "text" ? r.content : null))
      .catch((e: Error) => setError(e.message));
  }, [selected]);

  const buildable = useMemo(
    () => (selected ? templateVersion(selected.rel) : null),
    [selected]
  );

  const build = () => {
    if (!buildable) return;
    setBuilding(true);
    setResult(null);
    api
      .buildResumeTemplate(buildable)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBuilding(false));
  };

  if (selected) {
    const fileUrl = api.resumeTemplateFileUrl(selected.rel);
    const isHtml = selected.rel.toLowerCase().endsWith(".html");
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => {
              setSelected(null);
              setTextContent(null);
              setResult(null);
            }}
            className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-accent"
          >
            <ArrowLeft size={16} /> 返回列表
          </button>
          <span className="text-sm font-medium text-slate-200">{selected.rel}</span>
          <span className="text-xs text-slate-500">{fmtSize(selected.size)}</span>
          {buildable && (
            <button
              onClick={build}
              disabled={building}
              className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95 disabled:opacity-40"
            >
              {building ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Printer size={15} />
              )}
              {building ? "生成中…" : `生成 ${buildable} 的 PDF`}
            </button>
          )}
        </div>

        {error && (
          <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
            {error}
          </div>
        )}

        {result && (
          <div
            className={`rounded-2xl border p-4 ${
              result.passed ? "border-good/30 bg-good/10" : "border-bad/30 bg-bad/10"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold text-slate-200">
                {result.passed ? "生成成功，校验通过" : "生成完成，校验未通过"}
              </span>
              <span className="font-mono text-xs text-slate-400">
                {(result.size / 1024).toFixed(1)} KB · {result.a4.message}
              </span>
            </div>
            <ul className="mt-1 space-y-0.5 text-xs">
              {result.checks.map((c) => (
                <li key={c.label} className="flex items-center justify-between">
                  <span className="text-slate-400">{c.label}</span>
                  <span
                    className={
                      c.ok === null ? "text-slate-500" : c.ok ? "text-good" : "text-bad"
                    }
                  >
                    {c.value}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {isHtml ? (
          // 手写模板带相对资源（photo.jpg 等），用文件 URL 的 iframe 保真展示
          <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-2">
            <iframe
              src={fileUrl}
              title={selected.rel}
              className="h-[75vh] w-full rounded-xl border-0 bg-white"
            />
          </div>
        ) : textContent !== null ? (
          <pre className="max-h-[75vh] overflow-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-ink-950 p-5 font-mono text-xs leading-relaxed text-slate-300">
            {textContent}
          </pre>
        ) : (
          <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-2">
            <iframe
              src={fileUrl}
              title={selected.rel}
              className="h-[75vh] w-full rounded-xl border-0 bg-white"
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-400">
        手写 HTML 的精排版（高级模板）。只读浏览与生成；编辑仍走手写 HTML，改动后回到这里刷新预览。
      </p>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <p className="text-sm text-slate-400">
            02_简历工坊/ 下暂无文件。手写模板放 pdf/resume_&lt;版本&gt;.html。
          </p>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <button
              key={item.rel}
              onClick={() => setSelected(item)}
              className="group flex cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-ink-900/50 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-ink-850"
            >
              {fileIcon(item)}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-slate-200" title={item.rel}>
                  {item.rel}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">{fmtSize(item.size)}</div>
              </div>
              {templateVersion(item.rel) && (
                <span className="text-[10px] text-accent/70">可生成</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
