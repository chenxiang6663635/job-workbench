import { useEffect, useState } from "react";
import { CheckCircle2, Puzzle, Sparkles, TriangleAlert } from "lucide-react";
import { api, type GapResult } from "../api";

/**
 * JD↔简历差距面板。
 *
 * 设计核心是 injectable 与 missing 的措辞差异：
 * - injectable（可召回）：母版里有、这一版没用上 —— 是"召回"不是"编造"
 * - missing（真实缺口）：简历与母版都没有 —— 只能靠补经历，不能靠改词
 * 这组措辞把"补关键词"框定为诚实的行为，直接服务产品的诚实红线。
 */

const LEVEL_CLS: Record<string, string> = {
  Primary: "text-good",
  Secondary: "text-accent",
  Weak: "text-slate-500",
};

export default function GapPanel({ dir }: { dir: string }) {
  const [gap, setGap] = useState<GapResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError(null);
    // resume 不传 → 后端回退到最新版本，默认视图就是"当前版 vs 这个 JD"
    api
      .jobGap(dir)
      .then((r) => setGap(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [dir]);

  if (loading) {
    return (
      <div className="rounded-xl border border-white/10 bg-ink-950/40 p-5 text-xs text-slate-500">
        正在比对词典与简历…
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-xl border border-warn/30 bg-warn/5 p-5">
        <p className="text-xs text-warn">差距分析暂不可用</p>
        <p className="mt-1 text-xs leading-relaxed text-slate-500">{error}</p>
      </div>
    );
  }

  if (!gap) return null;

  const sections = [
    {
      key: "matched",
      icon: <CheckCircle2 size={14} className="text-good" />,
      title: "已覆盖",
      hint: "简历里能直接证明的词",
      cls: "border-good/25 bg-good/5",
      chip: "bg-good/10 text-good border-good/25",
    },
    {
      key: "injectable",
      icon: <Sparkles size={14} className="text-accent" />,
      title: "可召回",
      hint: "母版里有、这一版没用上——召回即可，不构成编造",
      cls: "border-accent/25 bg-accent/5",
      chip: "bg-accent/10 text-accent border-accent/25",
    },
    {
      key: "missing",
      icon: <TriangleAlert size={14} className="text-warn" />,
      title: "真实缺口",
      hint: "简历与母版都没有——需要评估是否补经历，而不是改词",
      cls: "border-warn/25 bg-warn/5",
      chip: "bg-warn/10 text-warn border-warn/25",
    },
  ] as const;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Puzzle size={15} className="text-accent" />
          <h4 className="text-sm font-medium text-slate-200">简历差距</h4>
        </div>
        <span className="text-[11px] text-slate-600">
          简历版本 {gap.resumeVersion} · 词典比对
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {sections.map((s) => {
          const count = gap.counts[s.key];
          const items =
            s.key === "matched"
              ? gap.matchedDetail
              : s.key === "injectable"
              ? gap.injectableDetail
              : gap.missingDetail;
          return (
            <div key={s.key} className={`rounded-xl border p-3.5 ${s.cls}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {s.icon}
                  <span className="text-xs font-medium text-slate-200">{s.title}</span>
                </div>
                <span className={`rounded-md border px-1.5 py-0.5 text-[11px] ${s.chip}`}>
                  {count}
                </span>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-slate-500">{s.hint}</p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {items.length === 0 && (
                  <span className="text-[11px] text-slate-600">无</span>
                )}
                {items.map((item) => {
                  const term = typeof item === "string" ? item : item.term;
                  const level = typeof item === "string" ? null : item.level;
                  return (
                    <span
                      key={term}
                      className={`rounded-md border border-white/10 bg-ink-950/60 px-2 py-1 text-[11px] text-slate-300 ${
                        s.key === "matched" ? "border-good/20" : ""
                      }`}
                      title={level ? `能力分层：${level}` : undefined}
                    >
                      {term}
                      {level && (
                        <span className={`ml-1 text-[10px] ${LEVEL_CLS[level] ?? ""}`}>
                          {level}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-slate-600">
        「可召回」的词来自你的母版事实，放进简历不构成编造；「真实缺口」的词
        母版里也没有，只能靠补真实经历——别硬写。
      </p>
    </div>
  );
}
