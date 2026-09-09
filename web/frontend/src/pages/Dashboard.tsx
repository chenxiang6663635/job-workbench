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
  Flame,
  Hourglass,
  Inbox,
  TrendingUp,
} from "lucide-react";
import {
  api,
  type DashboardData,
  type PendingItem,
  type StaleItem,
} from "../api";
import RetrospectivePanel from "../components/RetrospectivePanel";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Skeleton } from "../components/ui/skeleton";

// 数据可视化色板：阶段语义色，独立于主题 token（换主题不改图表语义）
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
  sort?: "health";
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
    ? "cursor-pointer hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10"
    : "";
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`group relative overflow-hidden rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5 text-left transition-all duration-300 disabled:cursor-default ${cls}`}
    >
      <div
        className="absolute -right-6 -top-6 h-24 w-24 rounded-full opacity-20 blur-2xl transition-opacity duration-300 group-hover:opacity-40"
        style={{ background: accent }}
      />
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className="mt-2 bg-gradient-to-b from-white to-primary/70 bg-clip-text text-3xl font-semibold text-transparent">
            {value}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
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
    <div className="rounded-lg border border-warning/25 bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Hourglass size={15} className="text-warn" />
        <h2 className="text-sm font-semibold text-foreground">静默提醒</h2>
        <span className="ml-auto text-[10px] text-muted-foreground">
          停留超过 {staleDays} 天无进展
        </span>
      </div>
      {stale.length === 0 ? (
        <p className="text-sm text-muted-foreground">没有长期无进展的活跃岗位。</p>
      ) : (
        <ul className="space-y-2">
          {stale.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between rounded-lg bg-warn/10 px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                <span className="text-foreground">
                  {s.公司} · {s.岗位}
                </span>
              </span>
              <span className="flex items-center gap-3 text-xs">
                <span className="font-mono text-warn">{s.days} 天</span>
                <span className="text-muted-foreground">{s.当前阶段}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// 健康度四态与追踪表同色同文案：颜色即严重度，理由整条列出（可核对优先）
const LEVEL_META: Record<
  string,
  { label: string; variant: "destructive" | "warning" | "default" }
> = {
  urgent: { label: "紧急", variant: "destructive" },
  overdue: { label: "逾期", variant: "warning" },
  stale: { label: "停滞", variant: "default" },
};

function PendingList({ pending }: { pending: PendingItem[] }) {
  return (
    <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Flame size={15} className="text-destructive" />
        <h2 className="text-sm font-semibold text-foreground">待推进</h2>
        <span className="ml-auto text-[10px] text-muted-foreground">
          健康度异常的活跃岗位
        </span>
      </div>
      {pending.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          没有待推进的记录——节奏很稳，继续保持。
        </p>
      ) : (
        <ul className="space-y-2">
          {pending.map((p) => {
            const meta = LEVEL_META[p.level] || LEVEL_META.stale;
            return (
              <li key={p.id}>
                <button
                  onClick={() => drillTo({ sort: "health", focusId: p.id })}
                  title="点击下钻到追踪表（按健康度排序）"
                  className="group w-full cursor-pointer rounded-lg bg-secondary/60 px-3 py-2 text-left transition-colors hover:bg-secondary"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-foreground transition-colors group-hover:text-accent">
                      {p.公司} · {p.岗位}
                    </span>
                    <Badge variant={meta.variant} className="shrink-0">
                      {meta.label}
                    </Badge>
                  </div>
                  {/* 理由整条亮出来：为什么该推进它，一目了然 */}
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {p.reasons.join("；")}
                  </p>
                </button>
              </li>
            );
          })}
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
      <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
        <AlertTriangle size={16} />
        加载看板失败：{error}
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    );
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
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            还没有任何投递记录
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            去「追踪表」添加第一家公司的投递记录，看板就会自动统计漏斗、待办与到期提醒。
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5 lg:col-span-2">
              <h2 className="mb-4 text-sm font-semibold text-foreground">
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
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--foreground) / 0.06)" }}
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 12,
                      color: "hsl(var(--foreground))",
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
                        fill={STAGE_COLORS[f.stage] ?? "hsl(var(--primary))"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-4">
              <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
                <h2 className="mb-3 text-sm font-semibold text-foreground">
                  按方向（点击查看该方向岗位）
                </h2>
                <div className="space-y-2">
                  {data.byDirection.map((d) => (
                    <ClickRow
                      key={d.key}
                      onClick={() => drillTo({ direction: d.key })}
                    >
                      <span className="text-muted-foreground">{d.key}</span>
                      <span className="font-mono text-accent">{d.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
                <h2 className="mb-3 text-sm font-semibold text-foreground">
                  按批次（点击查看该批次岗位）
                </h2>
                <div className="space-y-2">
                  {data.byBatch.map((b) => (
                    <ClickRow key={b.key} onClick={() => drillTo({ batch: b.key })}>
                      <span className="text-muted-foreground">{b.key}</span>
                      <span className="font-mono text-accent">{b.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">
                近七天待办
              </h2>
              {data.upcoming.length === 0 ? (
                <p className="text-sm text-muted-foreground">未来七天没有到期事项。</p>
              ) : (
                <ul className="space-y-2">
                  {data.upcoming.map((u) => (
                    <li
                      key={u.id + u.reason}
                      className="flex items-center justify-between gap-2 rounded-lg bg-secondary/60 px-3 py-2 text-sm"
                    >
                      <button
                        onClick={() => drillTo({ focusId: u.id })}
                        className="min-w-0 flex-1 cursor-pointer truncate text-left text-foreground transition-colors hover:text-accent"
                        title="查看该记录"
                      >
                        {u.公司} · {u.岗位}
                      </button>
                      <span className="flex shrink-0 items-center gap-2 text-xs">
                        <span className="text-muted-foreground">{u.reason}</span>
                        <span className="font-mono text-warn">{u.date}</span>
                        {u.reason === "下次动作" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => snooze(u.id, u.date)}
                            title="顺延 7 天"
                            className="h-6 px-1.5 text-[10px]"
                          >
                            顺延 7 天
                          </Button>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">
                已过截止日提醒
              </h2>
              {data.overdue.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  没有已过截止日且未投递的记录。
                </p>
              ) : (
                <ul className="space-y-2">
                  {data.overdue.map((o) => (
                    <li
                      key={o.id}
                      onClick={() => drillTo({ focusId: o.id })}
                      className="flex cursor-pointer items-center justify-between rounded-lg bg-destructive/10 px-3 py-2 text-sm"
                    >
                      <span className="text-foreground">
                        {o.公司} · {o.岗位}
                      </span>
                      <span className="font-mono text-xs text-destructive">
                        {o.截止日期}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <PendingList pending={data.pending} />
            <StaleList stale={data.stale} staleDays={data.staleDays} />
          </div>

          {/* 周期复盘（P3）：转化率 / 停留 / 归因——数据越攒越值钱 */}
          {data.retrospective && (
            <div className="rounded-lg border border-border bg-card/40 shadow-card ring-1 ring-white/5 p-5">
              <RetrospectivePanel data={data.retrospective} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
