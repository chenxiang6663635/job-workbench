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
import { AlertTriangle, Briefcase, CalendarClock, TrendingUp } from "lucide-react";
import { api, type DashboardData } from "../api";

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

function StatCard({
  label,
  value,
  hint,
  icon,
  accent,
}: {
  label: string;
  value: string | number;
  hint: string;
  icon: React.ReactNode;
  accent: string;
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/10 bg-gradient-to-br from-ink-850 to-ink-900 p-5 transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg hover:shadow-accent/10">
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
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

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
        />
        <StatCard
          label="流程中"
          value={data.active}
          hint="尚未结束的岗位"
          icon={<TrendingUp size={20} />}
          accent="#34d399"
        />
        <StatCard
          label="近七天待办"
          value={data.upcoming.length}
          hint="需要跟进的动作"
          icon={<CalendarClock size={20} />}
          accent="#fbbf24"
        />
        <StatCard
          label="已过截止"
          value={data.overdue.length}
          hint="待投但已过期"
          icon={<AlertTriangle size={20} />}
          accent="#f87171"
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
                投递漏斗
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
                  <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={18}>
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
                  按方向
                </h2>
                <div className="space-y-2">
                  {data.byDirection.map((d) => (
                    <div
                      key={d.key}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-slate-300">{d.key}</span>
                      <span className="font-mono text-accent">{d.count}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
                <h2 className="mb-3 text-sm font-semibold text-slate-200">
                  按批次
                </h2>
                <div className="space-y-2">
                  {data.byBatch.map((b) => (
                    <div
                      key={b.key}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-slate-300">{b.key}</span>
                      <span className="font-mono text-accent">{b.count}</span>
                    </div>
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
                      className="flex items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-sm transition-colors hover:bg-white/10"
                    >
                      <span className="text-slate-200">
                        {u.公司} · {u.岗位}
                      </span>
                      <span className="flex items-center gap-2 text-xs">
                        <span className="text-slate-500">{u.reason}</span>
                        <span className="font-mono text-warn">{u.date}</span>
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
                      className="flex items-center justify-between rounded-lg bg-bad/10 px-3 py-2 text-sm"
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
        </>
      )}
    </div>
  );
}
