import { useEffect, useState } from "react";
import { ArrowLeft, FileText, FileImage, FileCode2, Inbox } from "lucide-react";
import { api, type LibraryItem } from "../api";
import { Skeleton } from "../components/ui/skeleton";

// 简历文件（手写 HTML / 生成 PDF）已于 2026-09-03 迁往「简历工坊」页浏览，
// 素材库只保留事实库，避免与简历工坊同名混淆
const SECTION = "facts" as const;

function fileIcon(item: LibraryItem) {
  if (item.kind === "text") return <FileCode2 size={16} className="text-accent" />;
  const ext = item.name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileText size={16} className="text-destructive" />;
  return <FileImage size={16} className="text-warn" />;
}

function fmtSize(n: number) {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export default function Library() {
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<{
    rel: string;
    text?: string;
    fileUrl?: string;
    isBinary: boolean;
  } | null>(null);

  useEffect(() => {
    api
      .libraryList(SECTION)
      .then(
        (r) => setItems(r.items),
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  }, []);

  const open = (item: LibraryItem) => {
    setError(null);
    if (item.kind === "binary") {
      setView({ rel: item.rel, fileUrl: api.libraryFileUrl(SECTION, item.rel), isBinary: true });
      return;
    }
    api
      .libraryContent(SECTION, item.rel)
      .then((r) => setView({ rel: item.rel, text: r.content, isBinary: false }))
      .catch((e: Error) => setError(e.message));
  };

  if (view) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setView(null)}
            className="flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-accent"
          >
            <ArrowLeft size={16} /> 返回列表
          </button>
          <span className="text-sm font-medium text-foreground">{view.rel}</span>
        </div>

        {view.isBinary ? (
          <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-2">
            <iframe
              src={view.fileUrl}
              title={view.rel}
              className="h-[70vh] w-full rounded-xl border-0 bg-white"
            />
          </div>
        ) : (
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-background p-5 font-mono text-xs leading-relaxed text-muted-foreground">
            {view.text}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-foreground">事实库</span>
        <span className="text-xs text-muted-foreground">
          简历文件已迁往「简历工坊」页浏览
        </span>
        <span className="ml-auto text-sm text-muted-foreground">{items.length} 个文件</span>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-sm text-muted-foreground">事实库暂无事实卡</p>
        </div>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <button
              key={item.rel}
              onClick={() => open(item)}
              className="group flex cursor-pointer items-center gap-3 rounded-xl border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-secondary"
            >
              {fileIcon(item)}
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm text-foreground" title={item.rel}>
                  {item.name}
                </div>
                <div className="mt-0.5 text-xs text-muted-foreground">
                  {fmtSize(item.size)}
                </div>
              </div>
              {item.kind === "binary" && (
                <span className="text-xs text-muted-foreground/70">预览</span>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
