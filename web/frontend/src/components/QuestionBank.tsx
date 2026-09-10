import { useEffect, useState } from "react";
import { BookOpen, MessageSquareQuote, Search, Sparkles, X } from "lucide-react";
import { api, type QuestionGroup } from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";

// 轮次用小徽章标出，同一岗位的不同轮次问题一眼能分开
const ROUND_VARIANT: Record<string, "default" | "secondary" | "success"> = {
  笔试: "secondary",
  一面: "default",
  二面: "default",
  三面: "default",
  HR面: "success",
  终面: "success",
};

function QuestionCard({ item }: { item: QuestionGroup["items"][number] }) {
  return (
    <Card className="p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <Badge
          variant={ROUND_VARIANT[item.轮次] ?? "secondary"}
          className="rounded px-1.5 py-0.5 text-[11px]"
        >
          {item.轮次 || "未填轮次"}
        </Badge>
        {item.面试时间 && <span className="font-mono text-muted-foreground">{item.面试时间}</span>}
        {item.面试官 && <span className="text-muted-foreground">{item.面试官}</span>}
        {item.结果 && item.结果 !== "待定" && (
          <span className={item.结果 === "通过" ? "text-success" : "text-muted-foreground"}>
            {item.结果}
          </span>
        )}
      </div>

      {/* 三段式：问题 → 我的回答要点 → 复盘，与面试详情同一套视觉语言 */}
      <p className="flex gap-2 text-sm leading-relaxed text-foreground">
        <MessageSquareQuote size={14} className="mt-0.5 shrink-0 text-primary" />
        <span>{item.问题记录}</span>
      </p>
      {item.我的回答要点 && (
        <p className="mt-2 pl-6 text-xs leading-relaxed text-muted-foreground">
          <span className="mr-1 text-muted-foreground/70">我的回答</span>
          {item.我的回答要点}
        </p>
      )}
      {item.复盘与改进 && (
        <p className="mt-1.5 rounded-lg border border-warning/20 bg-warning/5 px-2 py-1.5 pl-6 text-xs leading-relaxed text-warning">
          复盘：{item.复盘与改进}
        </p>
      )}
    </Card>
  );
}

export default function QuestionBank() {
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 输入防抖：题库检索是纯前端过滤不划算（数据在后端 CSV 里），
  // 但也不能每敲一个字就打一次接口
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .questionBank(keyword.trim() || undefined)
        .then((r) => {
          setGroups(r.groups);
          setTotal(r.total);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [keyword]);

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜问题、回答或复盘关键词…"
          className="pl-9 pr-28"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            {loading ? "检索中…" : `共 ${total} 条`}
          </span>
          {keyword && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              title="清空"
              onClick={() => setKeyword("")}
            >
              <X size={13} />
            </Button>
          )}
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条 */}
      {loading && groups.length === 0 ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-2xl" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <Card className="flex flex-col items-center border-dashed p-10 text-center">
          <BookOpen size={28} className="mb-3 text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            {keyword ? "没有匹配的问题" : "题库还是空的"}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {keyword
              ? "换个关键词试试，或者清空搜索看全部。"
              : "面过之后在面试记录里填上「问题记录」，这里会攒下你被问过的问题——下次面试前可以照着过一遍。"}
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {groups.map((g) => (
            <Card key={`${g.公司}__${g.岗位}`} className="rounded-2xl p-4">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={14} className="text-primary" />
                <span className="text-sm font-semibold text-foreground">{g.公司}</span>
                {g.岗位 && <span className="text-xs text-muted-foreground">{g.岗位}</span>}
                <Badge variant="secondary" className="ml-auto text-[11px]">
                  {g.total} 条
                </Badge>
              </div>
              <div className="space-y-2">
                {g.items.map((item) => (
                  <QuestionCard key={item.id || item.问题记录} item={item} />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
