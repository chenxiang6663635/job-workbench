import { ChartNoAxesColumn, RotateCcw, ThumbsDown } from "lucide-react";
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
    </div>
  );
}
