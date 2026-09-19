import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type PrepContent, type PrepFile } from "../api";
import {
  buildNotesTree,
  NOTES_SECTIONS,
  type NotesNode,
  type NotesSectionKey,
} from "../lib/notes";
import { ErrorBanner } from "./ErrorBanner";
import NotesFileTree from "./NotesFileTree";
import NotesReader from "./NotesReader";
import { Card } from "./ui/card";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";

// 「笔记」页签的编排：两个 section 的列表、选中、内容与记忆。
// 外部编辑的刷新由 App 级 useWorkspaceSync（10s 指纹 → 整页 reload）承担，
// 本组件**不重复挂轮询**；reload 后靠 localStorage 记忆回到原文件。
// 列表与内容都只读（写通道在 approvals，本页不碰）。

const LAST_KEY = "jobws_notes_last";
const WS_KEY = "jobws_selected_workspace";

export interface NotesActive {
  section: NotesSectionKey;
  rel: string;
}

function readWorkspace(): string {
  try {
    return localStorage.getItem(WS_KEY) ?? "";
  } catch {
    return "";
  }
}

function readLast(ws: string): NotesActive | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw) as Record<string, NotesActive>;
    return all[ws] ?? null;
  } catch {
    return null;
  }
}

function writeLast(ws: string, active: NotesActive): void {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    const all = raw ? (JSON.parse(raw) as Record<string, NotesActive>) : {};
    all[ws] = active;
    localStorage.setItem(LAST_KEY, JSON.stringify(all));
  } catch {
    // 存储不可用：记忆失效无妨（不影响阅读）
  }
}

function findNode(nodes: NotesNode[], rel: string): NotesNode | null {
  for (const node of nodes) {
    if (node.kind === "file" && node.rel === rel) return node;
    if (node.kind === "dir") {
      const hit = findNode(node.children ?? [], rel);
      if (hit) return hit;
    }
  }
  return null;
}

function firstFileRel(nodes: NotesNode[]): string | null {
  for (const node of nodes) {
    if (node.kind === "file") return node.rel;
    const hit = firstFileRel(node.children ?? []);
    if (hit) return hit;
  }
  return null;
}

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
    const last = readLast(ws);
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

  // 内容加载：切换文件时取消上一次（回包乱序不覆盖新内容）
  useEffect(() => {
    if (!active) return;
    let cancelled = false;
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
  }, [active]);

  const onSelect = useCallback(
    (section: NotesSectionKey, node: NotesNode) => {
      const next = { section, rel: node.rel };
      setActive(next);
      writeLast(ws, next);
    },
    [ws]
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

  const activeNode = active ? findNode(tree[active.section], active.rel) : null;
  return (
    <div className="flex flex-1 flex-col gap-4 lg:flex-row lg:items-start">
      <NotesFileTree
        tree={tree}
        query={query}
        onQueryChange={setQuery}
        active={active}
        unreadable={unreadable}
        onSelect={onSelect}
      />
      <NotesReader
        section={active?.section ?? "interview"}
        file={activeNode}
        content={content}
        loading={contentLoading}
        error={contentError}
      />
    </div>
  );
}
