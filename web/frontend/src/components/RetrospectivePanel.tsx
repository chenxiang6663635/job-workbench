import { ChartNoAxesColumn, Layers, RotateCcw, ThumbsDown } from "lucide-react";
import type { Retrospective } from "../api";
import { Card } from "./ui/card";
import { Bar } from "./ui/bar";
import { Num } from "./ui/number";
import { useTranslation } from "react-i18next";
import { domainLabel } from "../lib/domainLabels";

/**
 * 周期复盘区块（P3 长期资产）。
 * - 转化率来自时间线重建的「到达过」，不是当前存量——存量会高估早期阶段
 * - 停留天数看中位数，个别搁置半年的记录会拉爆均值
 * - 失败归因只聚合「已挂/已放弃」；「我拒绝的 offer」是双向选择，单独列出
 */

function rateColor(rate: number | null): string {
  if (rate === null) return "text-muted-foreground";
  if (rate >= 50) return "text-success";
  if (rate >= 20) return "text-primary";
  return "text-warning";
}

/** 柱状条 CSS 颜色：与转化率文字同一套阈值（Bar 原语只收 CSS 颜色，不接 class） */
function barColor(rate: number | null): string {
  if (rate === null) return "hsl(var(--muted))";
  if (rate >= 50) return "hsl(var(--success) / 0.7)";
  if (rate >= 20) return "hsl(var(--primary) / 0.7)";
  return "hsl(var(--warning) / 0.7)";
}

export default function RetrospectivePanel({ data }: { data: Retrospective }) {
  const { t } = useTranslation();
  const reached = data.conversion.filter((c) => c.reached > 0);
  const clusters = data.failureClusters;
  // 聚类说明的显示层：有 noteCode 就按当前语言拼句，未登记的 code 回落后端原文
  const noteText = (c: typeof clusters): string => {
    if (!c) return "";
    if (c.noteCode === "too_few_samples") {
      return t("cluster.tooFewSamples", {
        total: c.noteParams?.total ?? c.total,
        min: c.noteParams?.min ?? c.minSamples,
      });
    }
    if (c.noteCode === "no_keywords") return t("cluster.noKeywords");
    return c.note;
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <RotateCcw size={15} className="text-primary" />
        <h3 className="text-sm font-semibold text-foreground">{t("retro.title")}</h3>
        <span className="text-[11px] text-muted-foreground">
          {t("retro.recordCount", { total: data.total })}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 转化率：只展示到达过的阶段，空阶段不凑数 */}
        <Card className="rounded-lg p-4">
          <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
            <ChartNoAxesColumn size={13} className="text-primary" /> {t("retro.conversionTitle")}
          </p>
          {reached.length === 0 ? (
            <p className="text-xs text-muted-foreground">{t("retro.conversionEmpty")}</p>
          ) : (
            <div className="space-y-2">
              {reached.map((c) => (
                <div key={c.stage} className="flex items-center gap-2 text-xs">
                  <span
                    className="w-24 shrink-0 truncate text-muted-foreground"
                    title={domainLabel("stage", c.stage, t)}
                  >
                    {domainLabel("stage", c.stage, t)}
                  </span>
                  <Bar
                    value={(c.rate ?? 0) / 100}
                    color={barColor(c.rate)}
                    height="sm"
                    className="flex-1"
                  />
                  <Num align="right" className={`w-24 shrink-0 ${rateColor(c.rate)}`}>
                    {c.rate === null ? "—" : `${c.rate}%`}
                    <span className="ml-1 text-[10px] text-muted-foreground">
                      {c.advanced}/{c.reached}
                    </span>
                  </Num>
                </div>
              ))}
            </div>
          )}
          <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground">
            {t("retro.conversionHint")}
          </p>
        </Card>

        {/* 停留 + 归因 */}
        <div className="space-y-4">
          {data.stay.length > 0 && (
            <Card className="rounded-lg p-4">
              <p className="mb-2.5 text-xs font-medium text-foreground">{t("retro.stayTitle")}</p>
              <div className="space-y-1.5">
                {data.stay.map((s) => (
                  <div key={s.stage} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">
                      {domainLabel("stage", s.stage, t)}
                    </span>
                    <span className="text-foreground">
                      {t("app.daysUnit", { count: s.median })}
                      <span className="ml-1.5 text-[10px] text-muted-foreground">
                        {t("retro.avgOf", { avg: s.avg, n: s.n })}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {data.failure.length > 0 && (
            <Card className="rounded-lg border-warning/25 bg-warning/5 p-4">
              <p className="mb-2.5 text-xs font-medium text-warning">{t("retro.failureTitle")}</p>
              <div className="space-y-1.5">
                {data.failure.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-foreground">{f.reason}</span>
                    <span className="text-muted-foreground">{t("retro.times", { count: f.count })}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {data.declined.length > 0 && (
            <Card className="rounded-lg border-success/25 bg-success/5 p-4">
              <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-success">
                <ThumbsDown size={12} /> {t("retro.declinedTitle")}
              </p>
              <div className="space-y-1.5">
                {data.declined.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-foreground">{f.reason}</span>
                    <span className="text-muted-foreground">{t("retro.times", { count: f.count })}</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 失败原因聚类（第三批）：回答「到底败在哪一类」。
          样本不足时明确说"暂不展示"，绝不硬凑分类——凑出来的归因比没有更害人 */}
      <Card className="rounded-lg p-4">
        <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Layers size={13} className="text-primary" /> {t("retro.clusterTitle")}
          {clusters?.shown && (
            <span className="ml-1 font-normal text-muted-foreground">
              {t("retro.clusterTotal", { total: clusters.total })}
            </span>
          )}
        </p>
        {!clusters || !clusters.shown ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {clusters ? noteText(clusters) || t("retro.clusterEmpty") : t("retro.clusterEmpty")}
          </p>
        ) : (
          <>
            {clusters.note && (
              <p className="mb-2 text-[11px] text-warning">{noteText(clusters)}</p>
            )}
            <div className="space-y-2">
              {clusters.clusters.map((c) => (
                <div key={c.category}>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate text-foreground" title={c.category}>
                      {c.category}
                    </span>
                    <Bar
                      value={c.count / Math.max(1, clusters.total)}
                      color="hsl(var(--destructive))"
                      height="sm"
                      className="flex-1"
                    />
                    <Num align="right" muted className="w-16 shrink-0">
                      {t("retro.times", { count: c.count })}
                      <span className="ml-1 text-[10px] text-muted-foreground">
                        {Math.round((c.count * 100) / Math.max(1, clusters.total))}%
                      </span>
                    </Num>
                  </div>
                  {c.examples.length > 0 && (
                    <p className="mt-1 pl-28 text-[11px] leading-relaxed text-muted-foreground">
                      {c.examples.join("；")}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground">
              {t("retro.clusterHint1")}
              <code>config/failure_keywords.txt</code>
              {t("retro.clusterHint2")}
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
