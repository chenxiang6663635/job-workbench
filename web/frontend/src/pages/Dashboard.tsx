import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import {
  Bar,
  BarChart,
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

// 投递状态语义色（分布图用）：与阶段色同源思路——图表语义独立于主题 token
const APPLY_STATE_COLORS = {
  未投递: "#475569",
  流程中: "#38bdf8",
  已终态: "#94a3b8",
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
  // 岗位池下钻：跳过去并直接打开该岗位详情（由 Jobs 页消费）
  focusDir?: string;
};

// 存储不可用时（隐私模式 / 禁用存储）setItem 会抛异常——不兜住的话连后面的
// 跳转都不执行，用户看到的是「点了没反应」。兜住后至少还能跳到目标页。
function writeDrill(filter: Drill) {
  try {
    sessionStorage.setItem("jobws_drill", JSON.stringify(filter));
  } catch {
    // 存储不可用：退化为不带下钻信息的跳转
  }
}

function drillTo(filter: Drill) {
  writeDrill(filter);
  window.location.hash = "applications";
}

function drillToJob(dir: string) {
  writeDrill({ focusDir: dir });
  window.location.hash = "jobs";
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
  const { t } = useTranslation();
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
          {t("common.view")} <ChevronRight size={14} />
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
      className="group flex w-full cursor-pointer items-center justify-between text-left text-sm transition-colors hover:text-primary"
    >
      {children}
      <ChevronRight
        size={14}
        className="text-muted-foreground/50 opacity-0 transition-all group-hover:translate-x-0.5 group-hover:opacity-100"
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
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-warning/25 bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Hourglass size={15} className="text-warning" />
        <h2 className="text-sm font-semibold text-foreground">{t("dash.staleTitle")}</h2>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {/* count 是给 i18next 选复数形式的，days 才是显示值——少传 count
              会直接显示 key 名 `dash.staleSubtitle`（冒烟时抓到过） */}
          {t("dash.staleSubtitle", { count: staleDays, days: staleDays })}
        </span>
      </div>
      {stale.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dash.staleEmpty")}</p>
      ) : (
        <ul className="space-y-2">
          {stale.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between rounded-lg bg-warning/10 px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-warning" />
                <span className="text-foreground">
                  {s.公司} · {s.岗位}
                </span>
              </span>
              <span className="flex items-center gap-3 text-xs">
                <span className="font-mono text-warning">{t("app.daysUnit", { count: s.days })}</span>
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
  { labelKey: TranslationKey; variant: "destructive" | "warning" | "default" }
> = {
  urgent: { labelKey: "app.healthUrgent", variant: "destructive" },
  overdue: { labelKey: "app.healthOverdue", variant: "warning" },
  stale: { labelKey: "app.healthStale", variant: "default" },
};

function PendingList({ pending }: { pending: PendingItem[] }) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Flame size={15} className="text-destructive" />
        <h2 className="text-sm font-semibold text-foreground">{t("dash.pendingTitle")}</h2>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {t("dash.pendingSubtitle")}
        </span>
      </div>
      {pending.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t("dash.pendingEmpty")}
        </p>
      ) : (
        <ul className="space-y-2">
          {pending.map((p) => {
            const meta = LEVEL_META[p.level] || LEVEL_META.stale;
            return (
              <li key={p.id}>
                <button
                  onClick={() => drillTo({ sort: "health", focusId: p.id })}
                  title={t("dash.pendingDrillHint")}
                  className="group w-full cursor-pointer rounded-lg bg-secondary/60 px-3 py-2 text-left transition-colors hover:bg-secondary"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-foreground transition-colors group-hover:text-primary">
                      {p.公司} · {p.岗位}
                    </span>
                    <Badge variant={meta.variant} className="shrink-0">
                      {t(meta.labelKey)}
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
  const { t } = useTranslation();
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
        {t("dash.loadFailed", { error })}
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
  const unappliedHigh = data.unappliedHigh ?? [];
  // 后端只回前 N 条，总数单独给——列表长度不再等于总数
  const unappliedHighTotal = data.unappliedHighTotal ?? unappliedHigh.length;
  const scoreByState = data.scoreByState ?? [];
  const hasScoreByState = scoreByState.some(
    (t) => t.unapplied + t.active + t.terminal > 0
  );
  const hasJobPoolSignal = unappliedHigh.length > 0 || hasScoreByState;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t("dash.total")}
          value={data.total}
          hint={t("dash.totalHint")}
          icon={<Briefcase size={20} />}
          accent="#38bdf8"
          onClick={() => drillTo({})}
        />
        <StatCard
          label={t("dash.active")}
          value={data.active}
          hint={t("dash.activeHint")}
          icon={<TrendingUp size={20} />}
          accent="#34d399"
          onClick={() => drillTo({ active: true })}
        />
        <StatCard
          label={t("dash.upcoming")}
          value={data.upcoming.length}
          hint={t("dash.upcomingHint")}
          icon={<CalendarClock size={20} />}
          accent="#fbbf24"
          onClick={() => drillTo({ dueWithin: 7 })}
        />
        <StatCard
          label={t("dash.overdue")}
          value={data.overdue.length}
          hint={t("dash.overdueHint")}
          icon={<AlertTriangle size={20} />}
          accent="#f87171"
          onClick={() => drillTo({ overdue: true })}
        />
      </div>

      {/* 岗位池视角的两块。它们与「有没有投递记录」无关——
          一个岗位都没投过时，高分未投恰恰是最该先看到的东西。 */}
      {hasJobPoolSignal && (
        <div className="space-y-4">
          {unappliedHigh.length > 0 && (
            <div className="rounded-lg border border-primary/30 bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
              <h2 className="text-sm font-semibold text-foreground">
                {t("dash.unappliedHigh", { count: unappliedHighTotal })}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("dash.unappliedHighHint")}
              </p>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                {unappliedHigh.slice(0, 6).map((j) => (
                  <button
                    key={j.dir}
                    type="button"
                    onClick={() => drillToJob(j.dir)}
                    title={j.dir}
                    className="flex cursor-pointer items-center justify-between gap-2 rounded-lg bg-background/60 px-3 py-2 text-left text-sm transition-colors hover:bg-secondary/60"
                  >
                    <span className="truncate text-foreground">
                      {j.company} · {j.role}
                    </span>
                    <span className="shrink-0 font-mono text-xs text-primary">
                      {j.score}
                    </span>
                  </button>
                ))}
              </div>
              {unappliedHighTotal > unappliedHigh.length && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {t("dash.unappliedHighMore", {
                    count: unappliedHighTotal - unappliedHigh.length,
                  })}
                </p>
              )}
            </div>
          )}

          {hasScoreByState && (
            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
              <h2 className="text-sm font-semibold text-foreground">
                {t("dash.scoreByState")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("dash.scoreByStateHint")}
              </p>
              <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                {/* 左边取值仍是中文（APPLY_STATE_COLORS 的键 = 数据值），
                    右边展示走 t()——「取值不翻、展示翻」各归各 */}
                {(
                  [
                    ["job.filterUnapplied", "未投递"],
                    ["job.filterActive", "流程中"],
                    ["job.filterTerminal", "已终态"],
                  ] as [TranslationKey, keyof typeof APPLY_STATE_COLORS][]
                ).map(([labelKey, value]) => (
                  <span key={value} className="inline-flex items-center gap-1.5">
                    <span
                      className="h-2.5 w-2.5 rounded-sm"
                      style={{ background: APPLY_STATE_COLORS[value] }}
                    />
                    {t(labelKey)}
                  </span>
                ))}
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={scoreByState}
                  layout="vertical"
                  margin={{ left: 8, right: 24 }}
                >
                  <XAxis type="number" hide />
                  <YAxis
                    type="category"
                    dataKey="tier"
                    width={84}
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
                    dataKey="unapplied"
                    stackId="state"
                    name={t("job.filterUnapplied")}
                    fill={APPLY_STATE_COLORS.未投递}
                    barSize={18}
                  />
                  <Bar
                    dataKey="active"
                    stackId="state"
                    name={t("job.filterActive")}
                    fill={APPLY_STATE_COLORS.流程中}
                    barSize={18}
                  />
                  {/* 不设 radius：圆角只能挂在一根 Bar 上，而哪一根是「最后一根」
                      取决于该档位有没有数据——挂上去就会出现「有的柱圆角、有的方角」 */}
                  <Bar
                    dataKey="terminal"
                    stackId="state"
                    name={t("job.filterTerminal")}
                    fill={APPLY_STATE_COLORS.已终态}
                    barSize={18}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {data.total === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            {t("dash.emptyTitle")}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("dash.emptyHint", { tracker: t("nav.applications") })}
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5 lg:col-span-2">
              <h2 className="mb-4 text-sm font-semibold text-foreground">
                {t("dash.funnelTitle")}
              </h2>
              {/* 纯 DOM 行，不是柱状图：数字要能**右对齐成一列**，与右侧
                  「按方向 / 按批次」同一种读数方式。柱状图的标签只能跟着柱尾走，
                  数据分布一不均就参差不齐（而这一栏的值本来就常常相等）。
                  条形仍按比例，另加一层轨道——数据少时也能看清「占了多少」。 */}
              <div className="space-y-2.5">
                {data.funnel.map((f) => (
                  <button
                    key={f.stage}
                    onClick={() => drillTo({ stage: f.stage })}
                    title={t("dash.funnelRowTitle", { stage: f.stage, count: f.count })}
                    className="group flex w-full cursor-pointer items-center gap-3 text-left"
                  >
                    <span className="w-12 shrink-0 text-xs text-muted-foreground transition-colors group-hover:text-primary">
                      {f.stage}
                    </span>
                    <span className="h-3.5 flex-1 overflow-hidden rounded-full bg-secondary/40">
                      <span
                        className="block h-full rounded-full"
                        style={{
                          width: `${Math.max(3, Math.round((f.count / maxFunnel) * 100))}%`,
                          background: STAGE_COLORS[f.stage] ?? "hsl(var(--primary))",
                        }}
                      />
                    </span>
                    <span className="w-6 shrink-0 text-right text-xs font-medium tabular-nums text-foreground">
                      {f.count}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
                <h2 className="mb-3 text-sm font-semibold text-foreground">
                  {t("dash.byDirection")}
                </h2>
                <div className="space-y-2">
                  {data.byDirection.map((d) => (
                    <ClickRow
                      key={d.key}
                      onClick={() => drillTo({ direction: d.key })}
                    >
                      <span className="text-muted-foreground">{d.key}</span>
                      <span className="font-mono text-primary">{d.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
                <h2 className="mb-3 text-sm font-semibold text-foreground">
                  {t("dash.byBatch")}
                </h2>
                <div className="space-y-2">
                  {data.byBatch.map((b) => (
                    <ClickRow key={b.key} onClick={() => drillTo({ batch: b.key })}>
                      <span className="text-muted-foreground">{b.key}</span>
                      <span className="font-mono text-primary">{b.count}</span>
                    </ClickRow>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">
                {t("dash.upcoming")}
              </h2>
              {data.upcoming.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("dash.upcomingEmpty")}</p>
              ) : (
                <ul className="space-y-2">
                  {data.upcoming.map((u) => (
                    <li
                      key={u.id + u.reason}
                      className="flex items-center justify-between gap-2 rounded-lg bg-secondary/60 px-3 py-2 text-sm"
                    >
                      <button
                        onClick={() => drillTo({ focusId: u.id })}
                        className="min-w-0 flex-1 cursor-pointer truncate text-left text-foreground transition-colors hover:text-primary"
                        title={t("dash.viewRecord")}
                      >
                        {u.公司} · {u.岗位}
                      </button>
                      <span className="flex shrink-0 items-center gap-2 text-xs">
                        <span className="text-muted-foreground">{u.reason}</span>
                        <span className="font-mono text-warning">{u.date}</span>
                        {u.reason === "下次动作" && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => snooze(u.id, u.date)}
                            title={t("dash.postpone7")}
                            className="h-6 px-1.5 text-[10px]"
                          >
                            {t("dash.postpone7")}
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
                {t("dash.overdueTitle")}
              </h2>
              {data.overdue.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {t("dash.overdueEmpty")}
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
