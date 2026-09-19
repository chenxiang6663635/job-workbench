import { BookOpen, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { PrepContent } from "../api";
import { cn } from "../lib/utils";
import {
  extractOutline,
  NOTES_SECTIONS,
  stripHtmlComments,
  type NotesNode,
  type NotesSectionKey,
} from "../lib/notes";
import { ErrorBanner } from "./ErrorBanner";
import NotesMarkdown from "./NotesMarkdown";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";

// 右栏阅读区：面包屑 + 渲染正文 + 本页大纲（xl 以上显示）。
// 大纲锚点用 onClick + scrollIntoView，**不能用原生 #hash 跳转**——App 是 hash
// 路由，未知 hash 会被 tabFromHash 判为无效并跳回看板（不是"跳过去但不动"）。

export interface NotesReaderProps {
  section: NotesSectionKey;
  file: NotesNode | null;
  content: PrepContent | null;
  loading: boolean;
  error: string | null;
  /** 勾选写回的失败信息（预览/落盘）——与内容加载错误分开显示 */
  toggleError: string | null;
  onToggleTask: (line: number) => void;
  /** 正在预览的行号（该勾选框呈 pending 禁用态） */
  pendingLine: number | null;
  /** 有写回流程在进行中：整篇勾选框禁用（连点不会弹出别的行的确认框） */
  locked: boolean;
}

export default function NotesReader({
  section,
  file,
  content,
  loading,
  error,
  toggleError,
  onToggleTask,
  pendingLine,
  locked,
}: NotesReaderProps) {
  const { t } = useTranslation();
  const dir = NOTES_SECTIONS.find((s) => s.key === section)?.dir ?? "";

  if (!file) {
    return (
      <div className="min-w-0 flex-1 rounded-lg border border-dashed border-border p-6">
        <EmptyState
          compact
          icon={<BookOpen size={20} />}
          title={t("notes.emptyTitle")}
          description={t("notes.emptyHint")}
        />
      </div>
    );
  }

  const parts = file.rel.split("/");
  const name = parts[parts.length - 1];
  const subPath = parts.slice(0, -1).join(" / ");
  // 先剥 HTML 注释再交给渲染与大纲——同一份文本，两侧行号才不会漂移
  const clean = content ? stripHtmlComments(content.content) : "";
  const outline = extractOutline(clean);
  const jump = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="min-w-0 flex-1 rounded-lg bg-card-gradient p-6 shadow-card ring-1 ring-highlight/5 lg:p-8">
      <p className="mb-3 font-mono text-[11px] text-muted-foreground">
        {dir}
        {subPath && ` / ${subPath}`} / {name}
      </p>

      {toggleError && (
        <div className="mb-3">
          <ErrorBanner message={toggleError} />
        </div>
      )}

      {error ? (
        <ErrorBanner message={error} />
      ) : loading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-5 w-full rounded" />
          ))}
        </div>
      ) : content && content.content.trim() === "" ? (
        <EmptyState
          compact
          icon={<FileText size={20} />}
          title={t("notes.emptyFileTitle")}
          description={t("notes.emptyFileHint")}
        />
      ) : content ? (
        <div className="flex gap-8">
          <div className="mx-auto min-w-0 max-w-[46rem] flex-1">
            <NotesMarkdown
              content={clean}
              onToggleTask={onToggleTask}
              pendingLine={pendingLine}
              locked={locked}
            />
            {content.truncated && (
              <p className="mt-6 rounded-md border border-warning/60 bg-secondary/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
                {t("notes.truncated")}
              </p>
            )}
          </div>
          {outline.length > 0 && (
            <nav
              className="sticky top-6 hidden w-40 shrink-0 self-start xl:block"
              aria-label={t("notes.outline")}
            >
              <p className="mb-2 text-[11px] font-medium text-muted-foreground">
                {t("notes.outline")}
              </p>
              <ul>
                {outline.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => jump(item.id)}
                      className={cn(
                        "block w-full cursor-pointer border-l-2 border-transparent py-0.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground",
                        item.level === 3 ? "pl-5" : "pl-2.5"
                      )}
                    >
                      {item.text}
                    </button>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>
      ) : null}
    </section>
  );
}
