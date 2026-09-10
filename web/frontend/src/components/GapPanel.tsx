import { useEffect, useState } from "react";
import { CheckCircle2, Puzzle, Sparkles, TriangleAlert } from "lucide-react";
import { api, type GapResult } from "../api";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";

/**
 * JD↔简历差距面板。
 *
 * 设计核心是 injectable 与 missing 的措辞差异：
 * - injectable（可召回）：母版里有、这一版没用上 —— 是"召回"不是"编造"
 * - missing（真实缺口）：简历与母版都没有 —— 只能靠补经历，不能靠改词
 * 这组措辞把"补关键词"框定为诚实的行为，直接服务产品的诚实红线。
 */

const LEVEL_CLS: Record<string, string> = {
  Primary: "text-success",
  Secondary: "text-primary",
  Weak: "text-muted-foreground",
};

/* 三段各自的语义色：徽章语气 + 卡片描边 + 图标色 */
const SECTIONS = [
  {
    key: "matched",
    icon: CheckCircle2,
    title: "已覆盖",
    hint: "简历里能直接证明的词",
    variant: "success",
    iconCls: "text-success",
    cardCls: "border-success/25 bg-success/5",
  },
  {
    key: "injectable",
    icon: Sparkles,
    title: "可召回",
    hint: "母版里有、这一版没用上——召回即可，不构成编造",
    variant: "default",
    iconCls: "text-primary",
    cardCls: "border-primary/25 bg-primary/5",
  },
  {
    key: "missing",
    icon: TriangleAlert,
    title: "真实缺口",
    hint: "简历与母版都没有——需要评估是否补经历，而不是改词",
    variant: "warning",
    iconCls: "text-warning",
    cardCls: "border-warning/25 bg-warning/5",
  },
] as const;

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

  if (loading) return <Skeleton className="h-32 w-full rounded-xl" />;
  // 差距分析失败不该是红色报错级：调性上属"这一段暂不可用"，其余页面照常用
  if (error) return <ErrorBanner tone="warning" message={`差距分析暂不可用：${error}`} />;
  if (!gap) return null;

  const itemsOf = (key: string) =>
    key === "matched"
      ? gap.matchedDetail
      : key === "injectable"
      ? gap.injectableDetail
      : gap.missingDetail;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Puzzle size={15} className="text-primary" />
          <h4 className="text-sm font-medium text-foreground">简历差距</h4>
        </div>
        <span className="text-[11px] text-muted-foreground/70">
          简历版本 {gap.resumeVersion} · 词典比对
        </span>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {SECTIONS.map((s) => {
          const Icon = s.icon;
          const items = itemsOf(s.key);
          return (
            <Card key={s.key} className={`rounded-xl p-3.5 ${s.cardCls}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Icon size={14} className={s.iconCls} />
                  <span className="text-xs font-medium text-foreground">{s.title}</span>
                </div>
                <Badge variant={s.variant} className="rounded-md px-1.5 py-0 text-[11px]">
                  {gap.counts[s.key]}
                </Badge>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{s.hint}</p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {items.length === 0 && (
                  <span className="text-[11px] text-muted-foreground/70">无</span>
                )}
                {items.map((item) => {
                  const term = typeof item === "string" ? item : item.term;
                  const level = typeof item === "string" ? null : item.level;
                  return (
                    <span
                      key={term}
                      className="rounded-md border border-border bg-background/60 px-2 py-1 text-[11px] text-foreground"
                      title={level ? `能力分层：${level}` : undefined}
                    >
                      {term}
                      {level && (
                        <span className={`ml-1 text-[10px] ${LEVEL_CLS[level] ?? "text-muted-foreground"}`}>
                          {level}
                        </span>
                      )}
                    </span>
                  );
                })}
              </div>
            </Card>
          );
        })}
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground/70">
        「可召回」的词来自你的母版事实，放进简历不构成编造；「真实缺口」的词
        母版里也没有，只能靠补真实经历——别硬写。
      </p>
    </div>
  );
}
