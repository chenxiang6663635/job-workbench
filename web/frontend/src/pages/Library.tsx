import { useEffect, useState } from "react";
import { ArrowLeft, FileText, FileImage, FolderOpen, FileCode2 } from "lucide-react";
import { api, type LibraryItem } from "../api";

type Section = "resumes" | "facts";

const SECTIONS: { key: Section; label: string }[] = [
  { key: "resumes", label: "简历工坊" },
  { key: "facts", label: "事实库" },
];

function fileIcon(item: LibraryItem) {
  if (item.kind === "text") return <FileCode2 size={16} className="text-accent" />;
  const ext = item.name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={16} className="text-bad" />;
  return <FileImage size={16} className="text-warn" />;
}

function fmtSize(n: number) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export default function Library() {
  const [section, setSection] = useState<Section>("resumes");
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<{
    rel: string;
    text?: string;
    fileUrl?: string;
    isBinary: boolean;
  } | null>(null);

  useEffect(() => {
    api
      .libraryList(section)
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message));
  }, [section]);

  const open = (item: LibraryItem) => {
    setError(null);
    if (item.kind === "binary") {
      setView({ rel: item.rel, fileUrl: api.libraryFileUrl(section, item.rel), isBinary: true });
      return;
    }
    api
      .libraryContent(section, item.rel)
      .then((r) => setView({ rel: item.rel, text: r.content, isBinary: false }))
      .catch((e: Error) => setError(e.message));
  };

  if (view) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setView(null)}
            className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-accent"
          >
            <ArrowLeft size={16} /> 返回列表
          </button>
          <span className="text-sm font-medium text-slate-200">{view.rel}</span>
        </div>

        {view.isBinary ? (
          <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-2">
            <iframe
              src={view.fileUrl}
              title={view.rel}
              className="h-[70vh] w-full rounded-xl border-0 bg-white"
            />
          </div>
        ) : (
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-ink-950 p-5 font-mono text-xs leading-relaxed text-slate-300">
            {view.text}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {SECTIONS.map((s) => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={`flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm transition-all duration-200 ${
              section === s.key
                ? "bg-accent/15 text-accent"
                : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
            }`}
          >
            <FolderOpen size={16} />
            {s.label}
          </button>
        ))}
        <span className="ml-auto text-sm text-slate-500">{items.length} 个文件</span>
      </div>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <p className="text-sm text-slate-400">
            {section === "resumes" ? "简历工坊暂无文件" : "事实库暂无事实卡"}
          </p>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <button
              key={item.rel}
              onClick={() => open(item)}
              className="group flex cursor-pointer items-center gap-3 rounded-xl border border-white/10 bg-ink-900/50 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-ink-850"
            >
              {fileIcon(item)}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-slate-200" title={item.rel}>
                  {item.name}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {fmtSize(item.size)}
                </div>
              </div>
              {item.kind === "binary" && (
                <span className="text-xs text-slate-600">预览</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
