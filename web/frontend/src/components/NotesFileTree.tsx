import type { ReactNode } from "react";
import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "../lib/utils";
import {
  filterNotes,
  NOTES_SECTIONS,
  type NotesNode,
  type NotesSectionKey,
} from "../lib/notes";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { Input } from "./ui/input";

// 左栏目录树：两个 section 分组 → 目录 / 文件。
// README 显示为「目录说明」、_模板_/_示例_ 淡显（角色来自 lib/notes.ts 的标记），
// 空文件与读不了的文件都带小标记——文件列表绝不静默吞东西。
// 过滤只按名称/路径（全文搜索是后续批次）。

const GROUP_LABEL: Record<NotesSectionKey, TranslationKey> = {
  interview: "notes.group.interview",
  knowledge: "notes.group.knowledge",
};

// 层级缩进：笔记目录通常 1–2 层，三档足够（更深归第三档）
function indent(depth: number): string {
  if (depth <= 0) return "pl-2";
  if (depth === 1) return "pl-5";
  return "pl-8";
}

export interface NotesFileTreeProps {
  tree: Record<NotesSectionKey, NotesNode[]>;
  query: string;
  onQueryChange: (value: string) => void;
  active: { section: NotesSectionKey; rel: string } | null;
  unreadable: string[];
  onSelect: (section: NotesSectionKey, node: NotesNode) => void;
}

export default function NotesFileTree({
  tree,
  query,
  onQueryChange,
  active,
  unreadable,
  onSelect,
}: NotesFileTreeProps) {
  const { t } = useTranslation();
  const hits = NOTES_SECTIONS.map((section) => ({
    section,
    nodes: filterNotes(tree[section.key], query),
  }));

  const renderNodes = (
    nodes: NotesNode[],
    section: NotesSectionKey,
    depth: number
  ): ReactNode =>
    nodes.map((node) => {
      if (node.kind === "dir") {
        return (
          <li key={node.rel}>
            <p className={cn("py-1 text-[11px] text-muted-foreground", indent(depth))}>
              {node.name}
            </p>
            <ul>{renderNodes(node.children ?? [], section, depth + 1)}</ul>
          </li>
        );
      }
      const isActive = active?.section === section && active.rel === node.rel;
      return (
        <li key={node.rel}>
          <button
            type="button"
            onClick={() => onSelect(section, node)}
            className={cn(
              "flex w-full cursor-pointer items-center gap-2 rounded-md border-l-2 border-transparent py-1.5 pr-2 text-left text-[13px] text-foreground transition-colors hover:bg-secondary",
              indent(depth),
              isActive && "border-primary bg-secondary font-medium"
            )}
          >
            <span
              className={cn(
                "truncate",
                (node.fileKind === "template" || node.fileKind === "example") &&
                  "text-muted-foreground"
              )}
            >
              {node.fileKind === "readme" ? t("notes.readmeLabel") : node.name}
            </span>
            {unreadable.includes(node.rel) && (
              <span className="ml-auto shrink-0 rounded-full border border-destructive/60 px-1.5 text-[10px] text-destructive">
                {t("notes.badgeUnreadable")}
              </span>
            )}
            {node.size === 0 && (
              <span className="ml-auto shrink-0 rounded-full border border-border px-1.5 text-[10px] text-muted-foreground">
                {t("notes.badgeEmpty")}
              </span>
            )}
          </button>
        </li>
      );
    });

  return (
    <aside className="w-full rounded-lg border border-border bg-card p-3 lg:w-[17.5rem] lg:shrink-0 lg:self-start">
      <div className="relative mb-2">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t("notes.searchPlaceholder")}
          // placeholder 不是可访问名称（axe 的 label 规则会报）——补 aria-label
          aria-label={t("notes.searchPlaceholder")}
          className="pl-9"
        />
      </div>
      <div className="max-h-[50vh] overflow-auto lg:max-h-[calc(100dvh-26rem)]">
        {hits.map(({ section, nodes }) =>
          nodes.length === 0 ? null : (
            <div key={section.key} className="mb-1">
              <p className="px-2 pb-0.5 pt-2 text-[11px] font-medium text-muted-foreground">
                {t(GROUP_LABEL[section.key])}
              </p>
              <ul>{renderNodes(nodes, section.key, 0)}</ul>
            </div>
          )
        )}
        {query.trim() !== "" && hits.every(({ nodes }) => nodes.length === 0) && (
          <p className="px-2 py-4 text-center text-xs text-muted-foreground">
            {t("notes.noMatch")}
          </p>
        )}
      </div>
    </aside>
  );
}
