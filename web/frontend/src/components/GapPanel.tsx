import { useEffect, useState } from "react";
import { CheckCircle2, Puzzle, Sparkles, TriangleAlert } from "lucide-react";
import { api, type GapResult } from "../api";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import { useTranslation } from "react-i18next";

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
    titleKey: "gap.matched",
    hintKey: "gap.matchedHint",
    variant: "success",
    iconCls: "text-success",
    cardCls: "border-success/25 bg-success/5",
  },
  {
    key: "injectable",
    icon: Sparkles,
    titleKey: "gap.injectable",
    hintKey: "gap.injectableHint",
    variant: "default",
    iconCls: "text-primary",
    cardCls: "border-primary/25 bg-primary/5",
  },
  {
    key: "missing",
    icon: TriangleAlert,
    titleKey: "gap.missing",
    hintKey: "gap.missingHint",
    variant: "warning",
    iconCls: "text-warning",
    cardCls: "border-warning/25 bg-warning/5",
  },
] as const;

export default function GapPanel({ dir }: { dir: string }) {
  const { t } = useTranslation();
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
  if (error)
    return <ErrorBanner tone="warning" message={t("gap.unavailable", { error })} />;
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
          <h4 className="text-sm font-medium text-foreground">{t("gap.title")}</h4>
        </div>
        <span className="text-[11px] text-muted-foreground/70">
          {t("gap.versionNote", { version: gap.resumeVersion })}
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
                  <span className="text-xs font-medium text-foreground">{t(s.titleKey)}</span>
                </div>
                <Badge variant={s.variant} className="rounded-md px-1.5 py-0 text-[11px]">
                  {gap.counts[s.key]}
                </Badge>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{t(s.hintKey)}</p>
              <div className="mt-2.5 flex flex-wrap gap-1.5">
                {items.length === 0 && (
                  <span className="text-[11px] text-muted-foreground/70">{t("gap.none")}</span>
                )}
                {items.map((item) => {
                  const term = typeof item === "string" ? item : item.term;
                  const level = typeof item === "string" ? null : item.level;
                  return (
                    <span
                      key={term}
                      className="rounded-md border border-border bg-background/60 px-2 py-1 text-[11px] text-foreground"
                      title={level ? t("gap.levelTitle", { level }) : undefined}
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
        {t("gap.footer")}
      </p>
    </div>
  );
}
