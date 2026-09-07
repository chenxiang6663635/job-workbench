import { useEffect, useState } from "react";
import { BookOpen, MessageSquareQuote, Search, Sparkles, X } from "lucide-react";
import { api, type QuestionGroup } from "../api";

// 轮次用小徽章标出，同一岗位的不同轮次问题一眼能分开
const ROUND_STYLE: Record<string, string> = {
  笔试: "bg-slate-500/15 text-slate-300",
  一面: "bg-accent/15 text-accent",
  二面: "bg-accent/15 text-accent",
  三面: "bg-accent/15 text-accent",
  HR面: "bg-good/15 text-good",
  终面: "bg-good/15 text-good",
};

function QuestionCard({ item }: { item: QuestionGroup["items"][number] }) {
  return (
    <div className="rounded-xl border border-white/5 bg-ink-950/60 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <span
          className={`rounded px-1.5 py-0.5 font-medium ${
            ROUND_STYLE[item.轮次] || "bg-white/10 text-slate-300"
          }`}
        >
          {item.轮次 || "未填轮次"}
        </span>
        {item.面试时间 && (
          <span className="font-mono text-slate-500">{item.面试时间}</span>
        )}
        {item.面试官 && <span className="text-slate-500">{item.面试官}</span>}
        {item.结果 && item.结果 !== "待定" && (
          <span
            className={
              item.结果 === "通过" ? "text-good" : "text-slate-400"
            }
          >
            {item.结果}
          </span>
        )}
      </div>

      {/* 三段式：问题 → 我的回答要点 → 复盘，与面试详情同一套视觉语言 */}
      <p className="flex gap-2 text-sm leading-relaxed text-slate-100">
        <MessageSquareQuote size={14} className="mt-0.5 shrink-0 text-accent" />
        <span>{item.问题记录}</span>
      </p>
      {item.我的回答要点 && (
        <p className="mt-2 pl-6 text-xs leading-relaxed text-slate-300">
          <span className="mr-1 text-slate-500">我的回答</span>
          {item.我的回答要点}
        </p>
      )}
      {item.复盘与改进 && (
        <p className="mt-1.5 rounded-lg border border-warn/20 bg-warn/5 px-2 py-1.5 pl-6 text-xs leading-relaxed text-warn">
          复盘：{item.复盘与改进}
        </p>
      )}
    </div>
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
      <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-ink-900 px-3">
        <Search size={14} className="text-slate-500" />
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜问题、回答或复盘关键词…"
          className="w-full max-w-sm bg-transparent py-2 text-sm text-slate-200 outline-none placeholder:text-slate-600"
        />
        {keyword && (
          <button
            onClick={() => setKeyword("")}
            className="cursor-pointer text-slate-500 transition-colors hover:text-slate-200"
            title="清空"
          >
            <X size={14} />
          </button>
        )}
        <span className="ml-auto whitespace-nowrap text-xs text-slate-500">
          {loading ? "检索中…" : `共 ${total} 条`}
        </span>
      </div>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          {error}
        </div>
      )}

      {!loading && groups.length === 0 && (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <BookOpen size={28} className="mx-auto mb-3 text-slate-500" />
          <p className="text-base font-medium text-slate-200">
            {keyword ? "没有匹配的问题" : "题库还是空的"}
          </p>
          <p className="mt-2 text-sm text-slate-400">
            {keyword
              ? "换个关键词试试，或者清空搜索看全部。"
              : "面过之后在面试记录里填上「问题记录」，这里会攒下你被问过的问题——下次面试前可以照着过一遍。"}
          </p>
        </div>
      )}

      <div className="space-y-4">
        {groups.map((g) => (
          <div
            key={`${g.公司}__${g.岗位}`}
            className="rounded-2xl border border-white/10 bg-ink-900/60 p-4"
          >
            <div className="mb-3 flex items-center gap-2">
              <Sparkles size={14} className="text-accent" />
              <span className="text-sm font-semibold text-slate-100">
                {g.公司}
              </span>
              {g.岗位 && (
                <span className="text-xs text-slate-400">{g.岗位}</span>
              )}
              <span className="ml-auto rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-slate-400">
                {g.total} 条
              </span>
            </div>
            <div className="space-y-2">
              {g.items.map((item) => (
                <QuestionCard key={item.id || item.问题记录} item={item} />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
