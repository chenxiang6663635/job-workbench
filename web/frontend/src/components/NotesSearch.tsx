import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type PrepSearch } from "../api";
import type { NotesSectionKey } from "../lib/notes";
import { ErrorBanner } from "./ErrorBanner";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

// 笔记全文搜索（文件名 + 正文）：输入框 + 结果列表，**自包含**——
// 防抖、请求与四种形态（检索中 / 命中 N 条 / 空态 / 截断）都在本组件内判定，
// 父组件只需持有关键词（据此决定左栏显示结果还是目录树）并接住"点中哪一条"。
//
// 结果是服务端口径的快照：写回 / 外部编辑之后会过期，所以不做持久化——
// reload 后回到空态（宁可让人再搜一次，也不要指向已不存在的行）。

export interface NotesSearchProps {
  keyword: string;
  onKeywordChange: (value: string) => void;
  onPick: (section: NotesSectionKey, rel: string, line: number) => void;
}

export default function NotesSearch({
  keyword,
  onKeywordChange,
  onPick,
}: NotesSearchProps) {
  const { t } = useTranslation();
  const [data, setData] = useState<PrepSearch | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
            <ul className="max-h-[22rem] space-y-0.5 overflow-y-auto">
              {data.items.map((hit) => (
                <li key={`${hit.section}/${hit.rel}/${hit.line}`}>
                  <button
                    type="button"
                    onClick={() => onPick(hit.section, hit.rel, hit.line)}
                    className="block w-full cursor-pointer rounded-md px-2 py-1.5 text-left transition-colors hover:bg-secondary"
                  >
                    {/* 文件名命中（正文没有）时正文行为空——退回显示文件名 */}
                    <span className="block truncate text-xs text-foreground">
                      {hit.text || hit.name}
                    </span>
                    <span className="block truncate font-mono text-[10.5px] text-muted-foreground">
                      {hit.rel} · {t("notes.hitLine", { line: hit.line })}
                      {hit.inName && !hit.text ? ` · ${t("notes.hitInName")}` : ""}
                    </span>
                  </button>
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
        </div>
      )}
    </div>
  );
}
