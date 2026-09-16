import { useEffect, useState } from "react";
import { ArrowLeft, Inbox } from "lucide-react";
import { api, type LibraryItem } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { FileCard } from "../components/FileCard";
import { EmptyState } from "../components/ui/empty";
import { PageHeader } from "../components/ui/page-header";
import { useTranslation } from "react-i18next";

// 简历文件（手写 HTML / 生成 PDF）已于 2026-09-03 迁往「简历工坊」页浏览，
// 素材库只保留事实库，避免与简历工坊同名混淆
const SECTION = "facts" as const;

export default function Library() {
  const { t } = useTranslation();
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
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setView(null)}
            className="-ml-2"
          >
            <ArrowLeft size={16} /> {t("common.back")}
          </Button>
          <span className="text-sm font-medium text-foreground">{view.rel}</span>
        </div>

        {view.isBinary ? (
          <Card className="p-2">
            <iframe
              src={view.fileUrl}
              title={view.rel}
              className="h-[70vh] w-full rounded-lg border-0 bg-white"
            />
          </Card>
        ) : (
          <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-background p-5 font-mono text-xs leading-relaxed text-muted-foreground">
            {view.text}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("lib.facts")}
        description={t("lib.movedNote", { page: t("nav.resume") })}
        actions={
          <span className="text-sm text-muted-foreground">
            {t("lib.fileCount", { count: items.length })}
          </span>
        }
      />

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条 */}
      {loading ? (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="border-dashed">
          <EmptyState
            icon={<Inbox size={20} />}
            title={t("lib.empty")}
            description={t("lib.emptyHint")}
          />
        </Card>
      ) : (
        /* 自适应网格（批 4）：列宽随容器伸缩，文件少时不摆成一排孤立卡、
           文件多时自然增加列数——比固定三列更「撑得住」页面 */
        <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(220px,1fr))]">
          {items.map((item) => (
            <FileCard
              key={item.rel}
              name={item.name}
              kind={item.kind}
              size={item.size}
              onClick={() => open(item)}
              badge={
                item.kind === "binary" ? (
                  <span className="shrink-0 text-xs text-muted-foreground">{t("lib.preview")}</span>
                ) : null
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
