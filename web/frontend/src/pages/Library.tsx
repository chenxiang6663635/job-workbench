import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Inbox } from "lucide-react";
import { api, type LibraryItem } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { FileCard } from "../components/FileCard";
import NotesMarkdown from "../components/NotesMarkdown";
import { EmptyState } from "../components/ui/empty";
import { PageHeader } from "../components/ui/page-header";
import { stripHtmlComments } from "../lib/notes";
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
    truncated?: boolean;
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

  // 打开详情的序号守卫：连点两个文件时先点的慢响应会把内容盖到后点的标题下，
  // 而界面上看不出冲突（只能凭内容判断自己点的是哪一个）
  const detailSeq = useRef(0);
  const open = (item: LibraryItem) => {
    setError(null);
    const seq = ++detailSeq.current;
    if (item.kind === "binary") {
      setView({ rel: item.rel, fileUrl: api.libraryFileUrl(SECTION, item.rel), isBinary: true });
      return;
    }
    api
      .libraryContent(SECTION, item.rel)
      .then(
        (r) => {
          if (seq !== detailSeq.current) return;
          setView({ rel: item.rel, text: r.content, truncated: r.truncated, isBinary: false });
        },
        (e: Error) => {
          if (seq === detailSeq.current) setError(e.message);
        }
      );
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
          /* 2026-09-18：文本改用与「笔记」相同的 Markdown 渲染——事实卡本身就是
             标准 md（表格/勾选框/注释齐全），同一份文件不该在两页有两种样子；
             保留原 <pre> 的滚动容器尺寸约束 */
          <div className="max-h-[70vh] overflow-auto rounded-lg border border-border bg-card-gradient p-5 shadow-card">
            <div className="mx-auto max-w-[46rem]">
              <NotesMarkdown content={stripHtmlComments(view.text ?? "")} />
              {view.truncated && (
                <p className="mt-6 rounded-md border border-warning/60 bg-secondary/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                  {t("lib.truncated")}
                </p>
              )}
            </div>
          </div>
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
