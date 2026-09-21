import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { ArrowLeft, Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type PrepSearch } from "../api";
import type { NotesSectionKey } from "../lib/notes";
import { cn } from "../lib/utils";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

// 笔记全文搜索（文件名 + 正文）：输入框 + 结果列表，**自包含**——
// 防抖、请求与四种形态（检索中 / 命中 N 条 / 空态 / 截断）都在本组件内判定，
// 父组件只需持有关键词（据此决定左栏显示结果还是目录树）并接住"点中哪一条"。
//
// 结果是服务端口径的快照：写回 / 外部编辑之后会过期，所以不做持久化——
// reload 后回到空态（宁可让人再搜一次，也不要指向已不存在的行）。
//
// 2026-09-21（批次 B-5/B-6）把"能搜到"补成"能导航"：
// · 结果**按文件分组**（组头是文件名，带命中数）——同一篇的多处命中不再散在列表里；
// · 命中词 `<mark>` 高亮；当前定位到的那条有底色（aria-current=location）；
// · ↑↓ 在结果间移动焦点、Enter 打开（按钮原生行为）；重复点击同一条也重新定位
//   （父组件的 nonce 机制）；
// · 底部固定「返回目录树」——搜索态会把左栏目录树整个替换掉，这里给明确的回头路。

export interface NotesSearchProps {
  keyword: string;
  onKeywordChange: (value: string) => void;
  onPick: (section: NotesSectionKey, rel: string, line: number) => void;
  /** 当前已打开并定位的命中（结果列表里高亮它）；null = 没有定位中的命中 */
  activeHit?: { section: string; rel: string; line: number | null } | null;
}

type Hit = PrepSearch["items"][number];

/** 命中片段里的关键词高亮（大小写不敏感；找不到就原样——后端也可能只命中文件名）。 */
function HighlightedText({ text, keyword }: { text: string; keyword: string }) {
  const needle = keyword.trim();
  if (!needle) return <>{text}</>;
  const index = text.toLowerCase().indexOf(needle.toLowerCase());
  if (index === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, index)}
      <mark className="rounded bg-primary/25 px-0.5 text-foreground">
        {text.slice(index, index + needle.length)}
      </mark>
      {text.slice(index + needle.length)}
    </>
  );
}

export default function NotesSearch({
  keyword,
  onKeywordChange,
  onPick,
  activeHit,
}: NotesSearchProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<PrepSearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLUListElement>(null);

  // 防抖 250ms（与题库「被问过的问题」同款）；空关键词不发请求——后端口径是
  // 返回空结果而不是报错，所以这里也不必为"没输入"准备错误态。
  useEffect(() => {
    const q = keyword.trim();
    if (!q) {
      setData(null);
      setError(null);
      setLoading(false);
      return;
    }
    // 回包乱序守卫：搜索是高频重发，先发的慢请求后到会覆盖新关键词的结果，
    // 界面就停在"输入框是 B、列表是 A"且不会自愈（与列表/内容加载同款写法）
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      api
        .prepSearch(q)
        .then((res) => {
          if (cancelled) return;
          setData(res);
          setError(null);
        })
        .catch((e: Error) => {
          if (cancelled) return;
          setData(null);
          setError(e.message);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [keyword]);

  // 按文件分组（保序：服务端已按相关度/位置排过，分组不重排组内顺序）
  const groups = useMemo(() => {
    const map = new Map<string, { rel: string; name: string; hits: Hit[] }>();
    for (const hit of data?.items ?? []) {
      const key = `${hit.section}/${hit.rel}`;
      const group = map.get(key);
      if (group) group.hits.push(hit);
      else map.set(key, { rel: hit.rel, name: hit.name, hits: [hit] });
    }
    return Array.from(map.values());
  }, [data]);

  const isActive = (hit: Hit) =>
    activeHit != null &&
    hit.section === activeHit.section &&
    hit.rel === activeHit.rel &&
    hit.line === activeHit.line;

  // ↑↓ 在结果间移动焦点（Enter 由按钮原生行为触发打开）。
  // 焦点不在列表里时不动——避免抢走输入框的方向键。
  const onListKeyDown = (event: ReactKeyboardEvent<HTMLUListElement>) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const buttons = Array.from(listRef.current?.querySelectorAll("button") ?? []);
    const currentIndex = buttons.findIndex((button) => button === document.activeElement);
    if (currentIndex === -1) return;
    event.preventDefault();
    const delta = event.key === "ArrowDown" ? 1 : -1;
    const nextIndex = Math.min(Math.max(currentIndex + delta, 0), buttons.length - 1);
    buttons[nextIndex]?.focus();
  };

  return (
    <div className="space-y-2 rounded-lg border border-border bg-card p-3">
      <div className="relative">
        {/* 放大镜与右侧状态压在框内（与左树过滤框同款）；placeholder 不是可访问
            名称，aria-label 必须补——axe 的 label 规则 */}
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={keyword}
          onChange={(event) => onKeywordChange(event.target.value)}
          placeholder={t("notes.searchFullPlaceholder")}
          aria-label={t("notes.searchFullPlaceholder")}
          className="pl-9 pr-24"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
          {/* 常驻的 live region：读屏要听得到"检索中 → 命中 N 条"的变化——
              live region 必须先在 DOM 里，后续变化才会被播报 */}
          <span aria-live="polite" className="text-[11px] text-muted-foreground">
            {loading
              ? t("notes.searching")
              : data
                ? t("notes.hitCount", { count: data.total })
                : ""}
          </span>
          {keyword && (
            <Button
              variant="ghost"
              size="icon"
              title={t("common.clear")}
              onClick={() => onKeywordChange("")}
              className="h-6 w-6"
            >
              <X size={13} />
            </Button>
          )}
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      {data && !error && (
        <div className="space-y-1">
          {data.items.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-muted-foreground">
              {t("notes.searchEmpty")}
            </p>
          ) : (
            <ul
              ref={listRef}
              onKeyDown={onListKeyDown}
              className="max-h-[22rem] space-y-1 overflow-y-auto"
            >
              {groups.map((group) => (
                <li key={group.rel}>
                  {/* 组头 = 文件名（含本文件命中数）：结果按文件归拢 */}
                  <p className="truncate px-2 pt-1.5 text-[11px] font-medium text-muted-foreground">
                    {group.name}
                    {/* 计数不加透明度：muted-foreground 在暗色下恰好贴着 4.5:1，
                        再叠 opacity 就掉到 4.49（axe serious，实测被 e2e 抓到） */}
                    <span className="ml-1 text-[10.5px]">×{group.hits.length}</span>
                  </p>
                  <ul className="space-y-0.5">
                    {group.hits.map((hit) => {
                      const active = isActive(hit);
                      return (
                        <li key={`${hit.section}/${hit.rel}/${hit.line}`}>
                          <button
                            type="button"
                            aria-current={active ? "location" : undefined}
                            onClick={() => onPick(hit.section, hit.rel, hit.line)}
                            className={cn(
                              "block w-full cursor-pointer rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary",
                              active && "bg-primary/10"
                            )}
                          >
                            {/* 文件名命中（正文没有）时正文行为空——退回显示文件名 */}
                            <span className="block truncate text-xs text-foreground">
                              <HighlightedText
                                text={hit.text || hit.name}
                                keyword={keyword}
                              />
                            </span>
                            <span className="block truncate font-mono text-[10.5px] text-muted-foreground">
                              {t("notes.hitLine", { line: hit.line })}
                              {hit.inName && !hit.text ? ` · ${t("notes.hitInName")}` : ""}
                            </span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </li>
              ))}
            </ul>
          )}
          {/* 截断与没搜全是两件事，分开说——都不静默 */}
          {data.truncated && (
            <p className="px-2 text-[11px] text-muted-foreground">
              {t("notes.hitCountTruncated", { count: data.items.length })}
            </p>
          )}
          {data.skipped.length > 0 && (
            <p className="px-2 text-[11px] text-muted-foreground">
              {t("notes.searchSkipped", { count: data.skipped.length })}
            </p>
          )}
          {/* 搜索态会把左栏目录树整个替换掉——给一条明确的回头路（B-6） */}
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start"
            onClick={() => onKeywordChange("")}
          >
            <ArrowLeft size={13} className="mr-1" />
            {t("notes.backToTree")}
          </Button>
        </div>
      )}
    </div>
  );
}
