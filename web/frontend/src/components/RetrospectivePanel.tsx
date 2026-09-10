import { ChartNoAxesColumn, Layers, RotateCcw, ThumbsDown } from "lucide-react";
import type { Retrospective } from "../api";
import { Card } from "./ui/card";

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

/** 柱状条：与转化率同一套阈值配色 */
function barColor(rate: number | null): string {
  if (rate === null) return "bg-muted";
  if (rate >= 50) return "bg-success/70";
  if (rate >= 20) return "bg-primary/70";
  return "bg-warning/70";
}

export default function RetrospectivePanel({ data }: { data: Retrospective }) {
  const reached = data.conversion.filter((c) => c.reached > 0);
  const clusters = data.failureClusters;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <RotateCcw size={15} className="text-primary" />
        <h3 className="text-sm font-semibold text-foreground">周期复盘</h3>
        <span className="text-[11px] text-muted-foreground/70">
          {data.total} 条记录 · 数据越攒越值钱
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 转化率：只展示到达过的阶段，空阶段不凑数 */}
        <Card className="rounded-xl p-4">
          <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
            <ChartNoAxesColumn size={13} className="text-primary" /> 阶段转化率
          </p>
          {reached.length === 0 ? (
            <p className="text-xs text-muted-foreground/70">还没有阶段流转数据</p>
          ) : (
            <div className="space-y-2">
              {reached.map((c) => (
                <div key={c.stage} className="flex items-center gap-2 text-xs">
                  <span className="w-12 shrink-0 text-muted-foreground">{c.stage}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary/60">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${barColor(c.rate)}`}
                      style={{ width: `${c.rate ?? 0}%` }}
                    />
                  </div>
                  <span className={`w-24 shrink-0 text-right ${rateColor(c.rate)}`}>
                    {c.rate === null ? "—" : `${c.rate}%`}
                    <span className="ml-1 text-[10px] text-muted-foreground/70">
                      {c.advanced}/{c.reached}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground/70">
            转化率按「到达过该阶段的记录里，有多少推进到了更晚阶段」计算，来自时间线而非当前快照。
          </p>
        </Card>

        {/* 停留 + 归因 */}
        <div className="space-y-4">
          {data.stay.length > 0 && (
            <Card className="rounded-xl p-4">
              <p className="mb-2.5 text-xs font-medium text-foreground">各阶段停留（中位天数）</p>
              <div className="space-y-1.5">
                {data.stay.map((s) => (
                  <div key={s.stage} className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{s.stage}</span>
                    <span className="text-foreground">
                      {s.median} 天
                      <span className="ml-1.5 text-[10px] text-muted-foreground/70">
                        平均 {s.avg} · {s.n} 次
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {data.failure.length > 0 && (
            <Card className="rounded-xl border-warning/25 bg-warning/5 p-4">
              <p className="mb-2.5 text-xs font-medium text-warning">失败归因</p>
              <div className="space-y-1.5">
                {data.failure.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-foreground">{f.reason}</span>
                    <span className="text-muted-foreground">{f.count} 次</span>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {data.declined.length > 0 && (
            <Card className="rounded-xl border-success/25 bg-success/5 p-4">
              <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-success">
                <ThumbsDown size={12} /> 我拒绝的 offer（双向选择，不计失败）
              </p>
              <div className="space-y-1.5">
                {data.declined.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-foreground">{f.reason}</span>
                    <span className="text-muted-foreground">{f.count} 次</span>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      {/* 失败原因聚类（第三批）：回答「到底败在哪一类」。
          样本不足时明确说"暂不展示"，绝不硬凑分类——凑出来的归因比没有更害人 */}
      <Card className="rounded-xl p-4">
        <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-foreground">
          <Layers size={13} className="text-primary" /> 失败原因聚类
          {clusters?.shown && (
            <span className="ml-1 font-normal text-muted-foreground/70">
              共 {clusters.total} 条失败记录
            </span>
          )}
        </p>
        {!clusters || !clusters.shown ? (
          <p className="text-xs leading-relaxed text-muted-foreground">
            {clusters?.note || "还没有可聚类的失败记录"}
          </p>
        ) : (
          <>
            {clusters.note && <p className="mb-2 text-[11px] text-warning">{clusters.note}</p>}
            <div className="space-y-2">
              {clusters.clusters.map((c) => (
                <div key={c.category}>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate text-foreground" title={c.category}>
                      {c.category}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary/60">
                      <div
                        className="h-full rounded-full bg-destructive/60 transition-all duration-500"
                        style={{
                          width: `${Math.round((c.count * 100) / Math.max(1, clusters.total))}%`,
                        }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right text-muted-foreground">
                      {c.count} 次
                      <span className="ml-1 text-[10px] text-muted-foreground/70">
                        {Math.round((c.count * 100) / Math.max(1, clusters.total))}%
                      </span>
                    </span>
                  </div>
                  {c.examples.length > 0 && (
                    <p className="mt-1 pl-28 text-[11px] leading-relaxed text-muted-foreground/70">
                      {c.examples.join("；")}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2.5 text-[11px] leading-relaxed text-muted-foreground/70">
              分类口径由工作区 <code>config/failure_keywords.txt</code> 决定，
              顺序自上而下匹配；改完刷新看板即生效。
            </p>
          </>
        )}
      </Card>
    </div>
  );
}
