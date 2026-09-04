import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  Briefcase,
  CalendarClock,
  ChevronRight,
  Hourglass,
  TrendingUp,
} from "lucide-react";
import { api, type DashboardData, type StaleItem } from "../api";
import RetrospectivePanel from "../components/RetrospectivePanel";

const STAGE_COLORS: Record<string, string> = {
  待投: "#64748b",
  已投: "#38bdf8",
  笔试: "#818cf8",
  一面: "#a78bfa",
  二面: "#c084fc",
  三面: "#e879f9",
  HR面: "#f472b6",
  offer: "#34d399",
  签约: "#10b981",
  已挂: "#f87171",
  已放弃: "#94a3b8",
};

// 下钻筛选：投递到 sessionStorage，追踪表页在 mount 时读取
type Drill = {
  stage?: string;
  direction?: string;
  batch?: string;
  active?: boolean;
  overdue?: boolean;
  dueWithin?: number;
  focusId?: string;
};

function drillTo(filter: Drill) {
  sessionStorage.setItem("jobws_drill", JSON.stringify(filter));
  window.location.hash = "applications";
}

// 日期 YYYY-MM-DD + n 天，返回同格式字符串；入参非法时返回原值
function shiftDate(iso: string, days: number): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const d = new Date(
    Number(m[1]),
    Number(m[2]) - 1,
    Number(m[3])
  );
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${mo}-${da}`;
}

function StatCard({
  label,
  value,
  hint,
  icon,
  accent,
  onClick,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
  accent: string;
  onClick?: () => void;
}) {
  const cls = onClick
    ? "cursor-pointer hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg hover:shadow-accent/10"
    : "";
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`group relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-ink-850 to-ink-900 p-5 text-left transition-all duration-300 disabled:cursor-default ${cls}`}
    >
      <div
        className="absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-20 blur-2xl transition-opacity duration-300 group-hover:opacity-40"
        style={{ background: accent }}
      />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-400">
            {label}
          </p>
          <p className="mt-2 text-3xl font-semibold text-white">{value}</p>
          <p className="mt-1 text-xs text-slate-500">{hint}</p>
        </div>
        <div
          className="flex h-10 w-10 items-center justify-center rounded-xl"
          style={{ background: `${accent}22`, color: accent }}
        >
          {icon}
        </div>
      </div>
      {onClick && (
        <span className="absolute bottom-3 right-4 flex items-center gap-1 text-xs font-medium opacity-0 transition-opacity duration-300 group-hover:opacity-100">
          查看 <ChevronRight size={14} />
        </span>
      )}
    </button>
  );
}

function ClickRow({
  children,
  onClick,
}: {
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group flex w-full cursor-pointer items-center justify-between text-left text-sm transition-colors hover:text-accent"
    >
      {children}
      <ChevronRight
        size={14}
        className="text-slate-600 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100"
      />
    </button>
  );
}

function StaleList({
  stale,
  staleDays,
}: {
  stale: StaleItem[];
  staleDays: number;
}) {
  return (
    <div className="rounded-2xl border border-warn/25 bg-ink-900/60 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Hourglass size={15} className="text-warn" />
        <h2 className="text-sm font-semibold text-slate-200">静默提醒</h2>
        <span className="ml-auto text-[10px] text-slate-500">
          停留超过 {staleDays} 天无进展
        </span>
      </div>
      {stale.length === 0 ? (
        <p className="text-sm text-slate-500">没有长期无进展的活跃岗位。</p>
      ) : (
        <ul className="space-y-2">
          {stale.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between rounded-lg bg-warn/10 px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                <span className="text-slate-200">
                  {s.公司} · {s.岗位}
                </span>
              </span>
              <span className="flex items-center gap-3 text-xs">
                <span className="font-mono text-warn">{s.days} 天</span>
                <span className="text-slate-500">{s.当前阶段}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    setError(null);
    api
      .dashboard()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [reloadKey]);

  // 把某条记录的下次动作日期顺延 n 天（仅对"下次动作"类待办开放）
  const snooze = (id: string, date: string) => {
    api
      .updateApplication(id, { 下次动作日期: shiftDate(date, 7) })
      .then(() => setReloadKey((k) => k + 1))
      .catch((e: Error) => setError(e.message));
  };

  if (error) {
    return (
      <div className="rounded-2xl border border-bad/30 bg-bad/10 p-4 text-sm text-bad">
        加载看板失败：{error}
      </div>
    );
  }

  if (!data) {
    return <div className="text-sm text-slate-400">正在读取投递数据…</div>;
  }

  const maxFunnel = Math.max(1, ...data.funnel.map((f) => f.count));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="投递总数"
          value={data.total}
          hint="所有记录在案的公司"
          icon={<Briefcase size={20} />}
          accent="#38bdf8"
          onClick={() => drillTo({})}
        />
        <StatCard
          label="流程中"
          value={data.active}
          hint="尚未结束的岗位"
          icon={<TrendingUp size={20} />}
          accent="#34d399"
          onClick={() => drillTo({ active: true })}
        />
        <StatCard
          label="近七天待办"
          value={data.upcoming.length}
          hint="需要跟进的动作"
          icon={<CalendarClock size={20} />}
          accent="#fbbf24"
          onClick={() => drillTo({ dueWithin: 7 })}
        />
        <StatCard
          label="已过截止"
          value={data.overdue.length}
          hint="待投但已过期"
          icon={<AlertTriangle size={20} />}
          accent="#f87171"
          onClick={() => drillTo({ overdue: true })}
        />
      </div>

      {data.total === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <p className="text-base font-medium text-slate-200">
            还没有任何投递记录
          </p>
          <p className="mt-2 text-sm text-slate-400">
            去「追踪表」添加第一家公司的投递记录，看板就会自动统计漏斗、待办与到期提醒。
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5 lg:col-span-2">
              <h2 className="mb-4 text-sm font-semibold text-slate-200">
                投递漏斗（点击柱子查看该阶段岗位）
              </h2>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart
                  data={data.funnel}
                  layout="vertical"
                  margin={{ left: 8, right: 24 }}
                >
                  <XAxis type="number" hide domain={[0, maxFunnel]} />
                  <YAxis
                    type="category"
                    dataKey="stage"
                    width={56}
                    tick={{ fill: "#94a3b8", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "#ffffff08" }}
                    contentStyle={{
                      background: "#131c30",
                      border: "1px solid #ffffff1a",
                      borderRadius: 12,
                      color: "#e2e8f0",
                      fontSize: 12,
                    }}
                  />
                  <Bar
                    dataKey="count"
                    radius={[0, 6, 6, 0]}
                    barSize={18}
                    onClick={(d) => {
                      const stage = (d as { stage?: string }).stage;
                      if (stage) drillTo({ stage });
                    }}
                    className="cursor-pointer"
                  >
                    {data.funnel.map((f) => (
                      <Cell
                        key={f.stage}
                        fill={STAGE_COLORS[f.stage] ?? "#38bdf8"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
                <h2 className="mb-3 text-sm font-semibold text-slate-200">
                  按方向（点击查看该方向岗位）
                </h2>
                <div className="space-y-2">
                  {data.byDirection.map((d) => (
                    <ClickRow
                      key={d.key}
                      onClick={() => drillTo({ direction: d.key })}
                    >
                      <span className="text-slate-300">{d.key}</span>
                      <span className="font-mono text-accent">{d.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
                <h2 className="mb-3 text-sm font-semibold text-slate-200">
                  按批次（点击查看该批次岗位）
                </h2>
                <div className="space-y-2">
                  {data.byBatch.map((b) => (
                    <ClickRow key={b.key} onClick={() => drillTo({ batch: b.key })}>
                      <span className="text-slate-300">{b.key}</span>
                      <span className="font-mono text-accent">{b.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
              <h2 className="mb-3 text-sm font-semibold text-slate-200">
                近七天待办
              </h2>
              {data.upcoming.length === 0 ? (
                <p className="text-sm text-slate-500">未来七天没有到期事项。</p>
              ) : (
                <ul className="space-y-2">
                  {data.upcoming.map((u) => (
                    <li
                      key={u.id + u.reason}
                      className="flex items-center justify-between gap-2 rounded-lg bg-white/5 px-3 py-2 text-sm"
                    >
                      <button
                        onClick={() => drillTo({ focusId: u.id })}
                        className="min-w-0 flex-1 cursor-pointer truncate text-left text-slate-200 transition-colors hover:text-accent"
                        title="查看该记录"
                      >
                        {u.公司} · {u.岗位}
                      </button>
                      <span className="flex shrink-0 items-center gap-2 text-xs">
                        <span className="text-slate-500">{u.reason}</span>
                        <span className="font-mono text-warn">{u.date}</span>
                        {u.reason === "下次动作" && (
                          <button
                            onClick={() => snooze(u.id, u.date)}
                            title="顺延 7 天"
                            className="cursor-pointer rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-slate-400 transition-colors hover:border-accent/40 hover:text-accent"
                          >
                            顺延 7 天
                          </button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
              <h2 className="mb-3 text-sm font-semibold text-slate-200">
                已过截止日提醒
              </h2>
              {data.overdue.length === 0 ? (
                <p className="text-sm text-slate-500">
                  没有已过截止日且未投递的记录。
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.overdue.map((o) => (
                    <li
                      key={o.id}
                      onClick={() => drillTo({ focusId: o.id })}
                      className="flex cursor-pointer items-center justify-between rounded-lg bg-bad/10 px-3 py-2 text-sm"
                    >
                      <span className="text-slate-200">
                        {o.公司} · {o.岗位}
                      </span>
                      <span className="font-mono text-xs text-bad">
                        {o.截止日期}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <StaleList stale={data.stale} staleDays={data.staleDays} />

          {/* 周期复盘（P3）：转化率 / 停留 / 归因——数据越攒越值钱 */}
          {data.retrospective && (
            <div className="rounded-2xl border border-white/10 bg-ink-900/40 p-5">
              <RetrospectivePanel data={data.retrospective} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
