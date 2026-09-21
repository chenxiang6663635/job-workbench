import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type PrepContent, type PrepFile } from "../api";
import {
  buildNotesTree,
  findNodeByRel,
  firstFileRel,
  NOTES_SECTIONS,
  readLastOpened,
  readWorkspace,
  writeLastOpened,
  type NotesActive,
  type NotesNode,
  type NotesSectionKey,
} from "../lib/notes";
import { readNotesUi, writeNotesUi } from "../lib/notesView";
import { useNotesToggle } from "../hooks/useNotesToggle";
import { ErrorBanner } from "./ErrorBanner";
import NotesFileTree from "./NotesFileTree";
import NotesReader from "./NotesReader";
import NotesSearch from "./NotesSearch";
import NotesToggleDialog from "./NotesToggleDialog";
import { Card } from "./ui/card";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";

// 「笔记」页签的编排：两个 section 的列表、选中、内容与记忆。
// 外部编辑的刷新由 App 级 useWorkspaceSync（10s 指纹 → 整页 reload）承担，
// 本组件**不重复挂轮询**；reload 后靠 localStorage 记忆回到原文件。
// 列表只读；唯一的"写"是勾选写回——两段式（预览 → 确认 → apply 落盘，
// 状态机 ToggleFlow），落盘通道只有 /api/approvals/apply 一条。

export default function NotesBrowser() {
  const { t } = useTranslation();
  const ws = useMemo(readWorkspace, []);
  // 三个输入态都从 sessionStorage 起步（A-6）：切页签会**卸载**本组件（Radix Tabs
  // 不 forceMount），不记住的话"去宣讲会看一眼再回来"就把搜索结果全清空了。
  const [restoredUi] = useState(() => readNotesUi(ws));
  const [items, setItems] = useState<Record<NotesSectionKey, PrepFile[]> | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [query, setQuery] = useState(restoredUi.query);
  const [active, setActive] = useState<NotesActive | null>(null);
  const [content, setContent] = useState<PrepContent | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [refreshTick, setRefreshTick] = useState(0);
  // 全文搜索：这里只持有关键词（据此决定左栏显示结果还是目录树）——防抖、请求
  // 与四种结果形态都在 NotesSearch 里自包含。focusLine = 点中的结果要定位到第几行。
  const [keyword, setKeyword] = useState(restoredUi.keyword);
  const [focusLine, setFocusLine] = useState<number | null>(restoredUi.focusLine);
  // 每次点搜索结果自增（B-5）：同一条重复点击时行号没变、effect 不会重跑——nonce 逼它重定位
  const [focusNonce, setFocusNonce] = useState(0);
  // 上一次加载的文件（section/rel）：只有换文件才撤正文，写回重拉时保留（A-2）
  const loadedKey = useRef<string | null>(null);

  // 勾选写回：预览 → 确认 → 落盘的状态机在 hooks/useNotesToggle（含跨切页签 /
  // 刷新的待确认恢复）。落盘成功后重拉正文——写后的真值在文件里，本地不做乐观翻转。
  const reload = useCallback(() => setRefreshTick((tick) => tick + 1), []);
  const {
    flow,
    toggleError,
    clearToggleError,
    onToggleTask,
    onConfirmToggle,
    onCancelToggle,
    batchMode,
    pending,
    onToggleBatchMode,
    onBatchSubmit,
    onClearPending,
  } = useNotesToggle(ws, active, reload);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.prepList("interview"), api.prepList("knowledge")])
      .then(([interview, knowledge]) => {
        if (!cancelled) {
          setItems({ interview: interview.items, knowledge: knowledge.items });
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setListError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const tree = useMemo(
    () =>
      items
        ? buildNotesTree(NOTES_SECTIONS.map((s) => ({ key: s.key, items: items[s.key] })))
        : null,
    [items]
  );

  // 默认选中：记忆优先（且文件仍存在）→ 第一个 section 的第一个文件（README 已由树置顶）
  useEffect(() => {
    if (!tree || active) return;
    const last = readLastOpened(ws);
    if (last && items?.[last.section]?.some((f) => f.rel === last.rel)) {
      setActive(last);
      return;
    }
    for (const section of NOTES_SECTIONS) {
      const rel = firstFileRel(tree[section.key]);
      if (rel) {
        setActive({ section: section.key, rel });
        return;
      }
    }
  }, [tree, active, items, ws]);

  // 输入态记忆：切页签 / 外部刷新回来仍是同一套过滤与搜索（A-6）
  useEffect(() => {
    writeNotesUi({ ws, keyword, query, focusLine });
  }, [ws, keyword, query, focusLine]);

  // 内容加载：切换文件时取消上一次（回包乱序不覆盖新内容）；refreshTick 用于
  // 写回成功后重拉（写后的真值在文件里，本地不做乐观翻转）。
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    // 只有**换文件**才撤旧正文：留着旧内容会让 NotesReader 的定位 effect 先按
    // **旧文件**的块算锚点、滚一次错位的位置（子组件的 effect 比本组件的先跑）。
    // 同一文件重拉（写回后的 refreshTick）则保留旧正文 + 局部 loading——撤掉正文
    // 会让卡片塌成骨架、把人打回文档顶部（A-2）。
    const key = `${active.section}/${active.rel}`;
    if (loadedKey.current !== key) {
      loadedKey.current = key;
      setContent(null);
    }
    setContentLoading(true);
    setContentError(null);
    api
      .prepContent(active.section, active.rel)
      .then((data) => {
        if (!cancelled) setContent(data);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setContent(null);
          setContentError(e.message);
          setUnreadable((prev) =>
            prev.includes(active.rel) ? prev : [...prev, active.rel]
          );
        }
      })
      .finally(() => {
        if (!cancelled) setContentLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active, refreshTick]);

  const onSelect = useCallback(
    (section: NotesSectionKey, node: NotesNode) => {
      const next = { section, rel: node.rel };
      // 换文件时清掉上一份写回的残留：错误横幅指向的是上一个文件，不该挂在新文件上
      onCancelToggle();
      clearToggleError();
      setFocusLine(null);
      setActive(next);
      writeLastOpened(ws, next);
    },
    [ws, onCancelToggle, clearToggleError]
  );

  // 点搜索结果：打开该文件并记下要定位的行（真定位在 NotesReader——那里才拿得到
  // 渲染后的块级行号）
  const onPickHit = useCallback(
    (section: NotesSectionKey, rel: string, line: number) => {
      const next = { section, rel };
      onCancelToggle();
      clearToggleError();
      setActive(next);
      setFocusLine(line);
      setFocusNonce((value) => value + 1);
      writeLastOpened(ws, next);
    },
    [ws, onCancelToggle, clearToggleError]
  );

  if (listError) {
    return <ErrorBanner message={t("notes.loadFailed", { reason: listError })} />;
  }
  if (!tree) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16 w-full rounded-lg" />
        ))}
      </div>
    );
  }
  const total = NOTES_SECTIONS.reduce((sum, s) => sum + (items?.[s.key].length ?? 0), 0);
  if (total === 0) {
    return (
      <Card className="border-dashed">
        <EmptyState
          icon={<BookOpen size={20} />}
          title={t("notes.emptyTitle")}
          description={t("notes.emptyHint")}
        />
      </Card>
    );
  }

  const activeNode = active ? findNodeByRel(tree[active.section], active.rel) : null;
  return (
    <div className="flex flex-1 flex-col gap-4 lg:flex-row lg:items-start">
      {/* 左栏吸顶（B-7）：读长文往下滚时目录树与搜索框不跟着滚走 */}
      <div className="flex w-full flex-col gap-3 lg:sticky lg:top-6 lg:w-[17.5rem] lg:shrink-0">
        <NotesSearch
          keyword={keyword}
          onKeywordChange={setKeyword}
          onPick={onPickHit}
          activeHit={
            active && focusLine != null
              ? { section: active.section, rel: active.rel, line: focusLine }
              : null
          }
        />
        {/* 搜着的时候结果列表替代目录树——两个列表并排会让人分不清哪个是哪个 */}
        {keyword.trim() ? null : (
          <NotesFileTree
            tree={tree}
            query={query}
            onQueryChange={setQuery}
            active={active}
            unreadable={unreadable}
            onSelect={onSelect}
          />
        )}
      </div>
      <NotesReader
        section={active?.section ?? "interview"}
        file={activeNode}
        content={content}
        loading={contentLoading}
        error={contentError}
        toggleError={toggleError}
        onToggleTask={onToggleTask}
        pendingLine={flow?.phase === "previewing" ? flow.lines[0] ?? null : null}
        locked={flow !== null}
        batchMode={batchMode}
        pending={pending}
        onToggleBatchMode={onToggleBatchMode}
        onSubmitBatch={onBatchSubmit}
        onClearPending={onClearPending}
        focusLine={focusLine}
        focusNonce={focusNonce}
        onBackToTree={
          keyword.trim()
            ? () => {
                setKeyword("");
                setFocusLine(null);
              }
            : undefined
        }
      />
      <NotesToggleDialog flow={flow} onConfirm={onConfirmToggle} onCancel={onCancelToggle} />
    </div>
  );
}
