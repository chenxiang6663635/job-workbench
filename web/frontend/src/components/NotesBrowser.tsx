import { useCallback, useEffect, useMemo, useState } from "react";
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
import { ErrorBanner } from "./ErrorBanner";
import NotesFileTree from "./NotesFileTree";
import NotesReader from "./NotesReader";
import NotesSearch from "./NotesSearch";
import NotesToggleDialog, { type ToggleFlow } from "./NotesToggleDialog";
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
  const [items, setItems] = useState<Record<NotesSectionKey, PrepFile[]> | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState<NotesActive | null>(null);
  const [content, setContent] = useState<PrepContent | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState<string | null>(null);
  const [unreadable, setUnreadable] = useState<string[]>([]);
  const [flow, setFlow] = useState<ToggleFlow | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  // 全文搜索：这里只持有关键词（据此决定左栏显示结果还是目录树）——防抖、请求
  // 与四种结果形态都在 NotesSearch 里自包含。focusLine = 点中的结果要定位到第几行。
  const [keyword, setKeyword] = useState("");
  const [focusLine, setFocusLine] = useState<number | null>(null);

  const ws = useMemo(readWorkspace, []);

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

  // 内容加载：切换文件时取消上一次（回包乱序不覆盖新内容）；refreshTick 用于
  // 写回成功后重拉（写后的真值在文件里，本地不做乐观翻转）。
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    // 先撤掉旧正文：换文件时若留着旧内容，NotesReader 的定位 effect 会先按
    // **旧文件**的块算锚点并滚一次错位的位置（子组件的 effect 比本组件的先跑）
    setContent(null);
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
      setFlow(null);
      setToggleError(null);
      setFocusLine(null);
      setActive(next);
      writeLastOpened(ws, next);
    },
    [ws]
  );

  // 点搜索结果：打开该文件并记下要定位的行（真定位在 NotesReader——那里才拿得到
  // 渲染后的块级行号）
  const onPickHit = useCallback(
    (section: NotesSectionKey, rel: string, line: number) => {
      const next = { section, rel };
      setFlow(null);
      setToggleError(null);
      setActive(next);
      setFocusLine(line);
      writeLastOpened(ws, next);
    },
    [ws]
  );

  // 勾选写回：点击 → 预览（签发令牌）→ 确认框 → 凭令牌落盘 → 重拉内容。
  // 与题库改题同一套两段式（落盘走唯一写通道 /api/approvals/apply）。
  const onToggleTask = useCallback(
    (line: number) => {
      // 有流程在进行中就不再接新点击：两个预览并发时，后到的响应决定弹窗显示
      // 哪一行——"点 A 弹出 B 的确认框"是错配；此时勾选框已整体禁用（locked）
      if (!active || flow) return;
      setToggleError(null);
      setFlow({ phase: "previewing", line });
      api
        .previewPrepToggle(active.section, active.rel, line)
        .then((p) =>
          setFlow({ phase: "confirm", line, token: p.token, summary: p.summary, diff: p.diff })
        )
        .catch((e: Error) => {
          setFlow(null);
          setToggleError(e.message);
        });
    },
    [active, flow]
  );

  const onConfirmToggle = useCallback(() => {
    if (!flow || flow.phase !== "confirm") return;
    const { line, token, summary, diff } = flow;
    setFlow({ phase: "applying", line, token, summary, diff });
    api
      .applyApproval(token)
      .then(() => {
        setFlow(null);
        setRefreshTick((tick) => tick + 1);
      })
      .catch((e: Error) => {
        setFlow(null);
        setToggleError(e.message);
      });
  }, [flow]);

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
      <div className="flex w-full flex-col gap-3 lg:w-[17.5rem] lg:shrink-0">
        <NotesSearch keyword={keyword} onKeywordChange={setKeyword} onPick={onPickHit} />
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
        pendingLine={flow?.phase === "previewing" ? flow.line : null}
        locked={flow !== null}
        focusLine={focusLine}
      />
      <NotesToggleDialog
        flow={flow}
        onConfirm={onConfirmToggle}
        onCancel={() => setFlow(null)}
      />
    </div>
  );
}
