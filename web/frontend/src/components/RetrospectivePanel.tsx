import { ChartNoAxesColumn, Layers, RotateCcw, ThumbsDown } from "lucide-react";
import type { Retrospective } from "../api";

/**
 * 周期复盘区块（P3 长期资产）。
 * - 转化率来自时间线重建的「到达过」，不是当前存量——存量会高估早期阶段
 * - 停留天数看中位数，个别搁置半年的记录会拉爆均值
 * - 失败归因只聚合「已挂/已放弃」；「我拒绝的 offer」是双向选择，单独列出
 */

function rateColor(rate: number | null): string {
  if (rate === null) return "text-slate-500";
  if (rate >= 50) return "text-good";
  if (rate >= 20) return "text-accent";
  return "text-warn";
}

export default function RetrospectivePanel({ data }: { data: Retrospective }) {
  const reached = data.conversion.filter((c) => c.reached > 0);
  const clusters = data.failureClusters;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <RotateCcw size={15} className="text-accent" />
        <h3 className="text-sm font-semibold text-white">周期复盘</h3>
        <span className="text-[11px] text-slate-600">
          {data.total} 条记录 · 数据越攒越值钱
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 转化率：只展示到达过的阶段，空阶段不凑数 */}
        <div className="rounded-xl border border-white/10 bg-ink-900/60 p-4">
          <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-slate-300">
            <ChartNoAxesColumn size={13} className="text-accent" /> 阶段转化率
          </p>
          {reached.length === 0 ? (
            <p className="text-xs text-slate-600">还没有阶段流转数据</p>
          ) : (
            <div className="space-y-2">
              {reached.map((c) => (
                <div key={c.stage} className="flex items-center gap-2 text-xs">
                  <span className="w-12 shrink-0 text-slate-400">{c.stage}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        (c.rate ?? 0) >= 50
                          ? "bg-good/70"
                          : (c.rate ?? 0) >= 20
                          ? "bg-accent/70"
                          : "bg-warn/70"
                      }`}
                      style={{ width: `${c.rate ?? 0}%` }}
                    />
                  </div>
                  <span className={`w-24 shrink-0 text-right ${rateColor(c.rate)}`}>
                    {c.rate === null ? "—" : `${c.rate}%`}
                    <span className="ml-1 text-[10px] text-slate-600">
                      {c.advanced}/{c.reached}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          )}
          <p className="mt-2.5 text-[11px] leading-relaxed text-slate-600">
            转化率按「到达过该阶段的记录里，有多少推进到了更晚阶段」计算，来自时间线而非当前快照。
          </p>
        </div>

        {/* 停留 + 归因 */}
        <div className="space-y-4">
          {data.stay.length > 0 && (
            <div className="rounded-xl border border-white/10 bg-ink-900/60 p-4">
              <p className="mb-2.5 text-xs font-medium text-slate-300">
                各阶段停留（中位天数）
              </p>
              <div className="space-y-1.5">
                {data.stay.map((s) => (
                  <div key={s.stage} className="flex items-center justify-between text-xs">
                    <span className="text-slate-400">{s.stage}</span>
                    <span className="text-slate-200">
                      {s.median} 天
                      <span className="ml-1.5 text-[10px] text-slate-600">
                        平均 {s.avg} · {s.n} 次
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.failure.length > 0 && (
            <div className="rounded-xl border border-warn/25 bg-warn/5 p-4">
              <p className="mb-2.5 text-xs font-medium text-warn">失败归因</p>
              <div className="space-y-1.5">
                {data.failure.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-slate-300">{f.reason}</span>
                    <span className="text-slate-400">{f.count} 次</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.declined.length > 0 && (
            <div className="rounded-xl border border-good/25 bg-good/5 p-4">
              <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-good">
                <ThumbsDown size={12} /> 我拒绝的 offer（双向选择，不计失败）
              </p>
              <div className="space-y-1.5">
                {data.declined.map((f) => (
                  <div key={f.reason} className="flex items-center justify-between text-xs">
                    <span className="text-slate-300">{f.reason}</span>
                    <span className="text-slate-400">{f.count} 次</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 失败原因聚类（第三批）：回答「到底败在哪一类」。
          样本不足时明确说"暂不展示"，绝不硬凑分类——凑出来的归因比没有更害人 */}
      <div className="rounded-xl border border-white/10 bg-ink-900/60 p-4">
        <p className="mb-2.5 flex items-center gap-1.5 text-xs font-medium text-slate-300">
          <Layers size={13} className="text-accent" /> 失败原因聚类
          {clusters?.shown && (
            <span className="ml-1 font-normal text-slate-600">
              共 {clusters.total} 条失败记录
            </span>
          )}
        </p>
        {!clusters || !clusters.shown ? (
          <p className="text-xs leading-relaxed text-slate-500">
            {clusters?.note || "还没有可聚类的失败记录"}
          </p>
        ) : (
          <>
            {clusters.note && (
              <p className="mb-2 text-[11px] text-warn">{clusters.note}</p>
            )}
            <div className="space-y-2">
              {clusters.clusters.map((c) => (
                <div key={c.category}>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate text-slate-300" title={c.category}>
                      {c.category}
                    </span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/5">
                      <div
                        className="h-full rounded-full bg-bad/60 transition-all duration-500"
                        style={{
                          width: `${Math.round((c.count * 100) / Math.max(1, clusters.total))}%`,
                        }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right text-slate-400">
                      {c.count} 次
                      <span className="ml-1 text-[10px] text-slate-600">
                        {Math.round((c.count * 100) / Math.max(1, clusters.total))}%
                      </span>
                    </span>
                  </div>
                  {c.examples.length > 0 && (
                    <p className="mt-1 pl-28 text-[11px] leading-relaxed text-slate-600">
                      {c.examples.join("；")}
                    </p>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-2.5 text-[11px] leading-relaxed text-slate-600">
              分类口径由工作区 <code>config/failure_keywords.txt</code> 决定，
              顺序自上而下匹配；改完刷新看板即生效。
            </p>
          </>
        )}
      </div>
    </div>
  );
}
