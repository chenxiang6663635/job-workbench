import { useEffect, useMemo, useRef } from "react";
import { BookOpen, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { PrepContent } from "../api";
import { cn } from "../lib/utils";
import {
  extractOutline,
  findAnchorLine,
  NOTES_SECTIONS,
  readWorkspace,
  stripHtmlComments,
  type NotesNode,
  type NotesSectionKey,
} from "../lib/notes";
import { captureNotesPos, readNotesPos, restoreNotesPos } from "../lib/notesView";
import { ErrorBanner } from "./ErrorBanner";
import NotesMarkdown from "./NotesMarkdown";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";

// 右栏阅读区：面包屑 + 渲染正文 + 本页大纲（xl 以上显示）。
// 大纲锚点用 onClick + scrollIntoView，**不能用原生 #hash 跳转**——App 是 hash
// 路由，未知 hash 会被 tabFromHash 判为无效并跳回看板（不是"跳过去但不动"）。

// 命中块的视觉标记（token 类）：搜索点进来之后，滚过去就能看清是哪一处。
const HIT_CLASS = ["rounded", "bg-primary/10", "ring-1", "ring-primary/30"];

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
  /** 搜索命中的行号（1-based）：非 null 时滚到所属块并标记；null = 不定位 */
  focusLine: number | null;
  /** 每次「点搜索结果」自增：同一条重复点击也要重新定位（行号没变时 effect 不重跑） */
  focusNonce: number;
  /** 回目录树（搜索态下路径行的目录段可点）：清搜索、左栏换回目录树 */
  onBackToTree?: () => void;
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
  focusLine,
  focusNonce,
  onBackToTree,
}: NotesReaderProps) {
  const { t } = useTranslation();
  const dir = NOTES_SECTIONS.find((s) => s.key === section)?.dir ?? "";
  const ws = useMemo(readWorkspace, []);
  // 先剥 HTML 注释再交给渲染与大纲——同一份文本，两侧行号才不会漂移。
  // 两处都按正文 memo（A-3）：它们都是整篇扫描，此前每次交互（展开答案、勾选预览）
  // 都要重跑一遍——长笔记在窄屏上的卡顿就是这么来的。位置刻意在所有早退**之前**：
  // hooks 必须在每次渲染里同序调用。
  const clean = useMemo(() => (content ? stripHtmlComments(content.content) : ""), [content]);
  const outline = useMemo(() => extractOutline(clean), [clean]);

  // 搜索命中后的定位：命中行 → 它所属的块（起始行 ≤ 它的最后一个块）→ 滚过去并
  // 标记。**用 DOM 不用 hash 跳转**：App 是 hash 路由，原生 #hash 会被判无效并
  // 踢回看板（大纲按钮同一条约束）。块级行号由渲染侧挂在 `data-line` 上。
  // 位置刻意在所有早退**之前**——hooks 必须在每次渲染里同序调用。
  useEffect(() => {
    if (focusLine == null) return;
    const lines = Array.from(document.querySelectorAll("[data-line]"))
      .map((el) => Number(el.getAttribute("data-line")))
      .filter((n) => Number.isFinite(n));
    const anchor = findAnchorLine(lines, focusLine);
    if (anchor == null) return;
    const el = document.querySelector(`[data-line="${anchor}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add(...HIT_CLASS);
    return () => el.classList.remove(...HIT_CLASS);
    // focusNonce：同一条结果重复点击时行号没变，靠它逼 effect 重跑（重新滚 + 重新标记）
  }, [focusLine, focusNonce, content]);

  // 阅读位置记忆（A-2）：滚动时把"视口顶部所在的块"记下来（节流 400ms）。写回后的
  // 重拉、外部编辑触发的整页 reload 都靠它回到原处——此前两者都会把人打回顶部。
  // 写在滚动里而不是卸载时，是为了绕开"卸载时 DOM 还在不在"的不确定性。
  useEffect(() => {
    if (!file || !content) return;
    let timer = 0;
    const onScroll = () => {
      if (timer) return;
      timer = window.setTimeout(() => {
        timer = 0;
        captureNotesPos(ws, section, file.rel);
      }, 400);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("scroll", onScroll);
    };
  }, [file, content, section, ws]);

  // 位置恢复：内容就绪后**每个文件只做一次**——追着滚动条回位置会让页面自己抖。
  // 有搜索命中时让位：那是用户刚点过的明确目标，优先级更高。
  const restoredKey = useRef<string | null>(null);
  useEffect(() => {
    if (!content || loading || !file || focusLine != null) return;
    const key = `${section}/${file.rel}`;
    if (restoredKey.current === key) return;
    const pos = readNotesPos(ws);
    if (!pos || pos.section !== section || pos.rel !== file.rel) return;
    restoredKey.current = key;
    // rAF：等这一帧布局稳定（data-line 的块已经渲染完）再算目标位置
    requestAnimationFrame(() => restoreNotesPos(pos));
  }, [content, loading, file, focusLine, section, ws]);

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
  const jump = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <section className="min-w-0 flex-1 rounded-lg bg-card-gradient p-6 shadow-card ring-1 ring-highlight/5 lg:p-8">
      {/* 路径行（B-6）：搜索态下首段（目录名）可点 = 回目录树——「我在哪、怎么回去」
          在正文区也答得上，不用回左栏找入口 */}
      <div className="mb-3 flex flex-wrap items-baseline gap-x-1 font-mono text-[11px] text-muted-foreground">
        {onBackToTree ? (
          <button
            type="button"
            onClick={onBackToTree}
            title={t("notes.backToTree")}
            className="cursor-pointer transition-colors hover:text-foreground hover:underline"
          >
            {dir}
          </button>
        ) : (
          <span>{dir}</span>
        )}
        {subPath && <span>/ {subPath}</span>}
        <span className="text-foreground">/ {name}</span>
      </div>

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
