import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSeq } from "../hooks/useSeq";
import { DRILL_KEY, PREPARE_TAB_KEY, drillToJob } from "../lib/pageDrill";
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
  Hourglass,
  TrendingUp,
} from "lucide-react";
import {
  api,
  type DashboardData,
  type StaleItem,
} from "../api";
import ActivityFeed from "../components/ActivityFeed";
import { ErrorBanner } from "../components/ErrorBanner";
import RetrospectivePanel from "../components/RetrospectivePanel";
import { UpcomingTalks } from "../components/UpcomingTalks";
import { EmptyOnboarding } from "../components/OnboardingWizard";
import { domainLabel } from "../lib/domainLabels";
import { DashboardPendingList } from "../components/DashboardPendingList";
import { BarList } from "../components/ui/bar-list";
import { Button } from "../components/ui/button";
import { Num, StatValue } from "../components/ui/number";
import { Segmented } from "../components/ui/segmented";
import { EmptyState } from "../components/ui/empty";
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";

// 数据可视化色板（批 4 起走主题 token）：阶段语义映射到 --chart-* 与状态色——
// 图表与卡片同一套色源，换主题时跟着走（内联值不再出现，check_themes 验对比度）。
// 未登记的阶段会回退主色（见漏斗渲染的 ?? 兜底）——新增阶段时同步补在这里，
// 否则漏斗图里它会与所有未登记值同色、分不清。
const STAGE_COLORS: Record<string, string> = {
  待投: "hsl(var(--chart-6))",
  已投: "hsl(var(--chart-1))",
  测评: "hsl(var(--chart-7))",
  笔试: "hsl(var(--chart-7))",
  AI面: "hsl(var(--chart-5))",
  群面: "hsl(var(--chart-5))",
  一面: "hsl(var(--chart-5))",
  二面: "hsl(var(--chart-5))",
  三面: "hsl(var(--chart-5))",
  HR面: "hsl(var(--chart-4))",
  终面: "hsl(var(--chart-4))",
  offer: "hsl(var(--chart-2))",
  签约: "hsl(var(--chart-2))",
  已挂: "hsl(var(--destructive))",
  已放弃: "hsl(var(--muted-foreground))",
};

// 投递状态语义色（分布图用）：同源 token——未投递取描边档（最弱）、
// 流程中取主序列色、已终态取末位序列色。
const APPLY_STATE_COLORS = {
  未投递: "hsl(var(--border-strong))",
  流程中: "hsl(var(--chart-1))",
  已终态: "hsl(var(--chart-8))",
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
    sessionStorage.setItem(DRILL_KEY, JSON.stringify(filter));
  } catch {
    // 存储不可用：退化为不带下钻信息的跳转
  }
}

function drillTo(filter: Drill) {
  writeDrill(filter);
  window.location.hash = "applications";
}

// 宣讲会在「准备」板块的页签里：目标页 mount 时读这个键（读过即清）。
// 与 writeDrill 的 jobws_drill 是两个协议——那边的消费方是追踪表 / 岗位池。
function drillToPrepare() {
  try {
    sessionStorage.setItem(PREPARE_TAB_KEY, "talks");
  } catch {
    // 存储不可用：退化为落在「准备」的默认页签（恰好就是宣讲会）
  }
  window.location.hash = "prepare";
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
    ? "cursor-pointer hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-elev-2"
    : "";
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={`group relative overflow-hidden rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5 text-left transition-all duration-300 disabled:cursor-default ${cls}`}
    >
      {/* 彩色光斑已删（2026-09-17 数字体系重做）：与数字抢焦点、浅色卡上显脏；
          强调交给 icon 底色与主数字本身（方向 A：装饰能删就删） */}
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <div className="mt-2">
            <StatValue value={value} />
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </div>
        <div
          className="flex h-10 w-10 items-center justify-center rounded-lg"
          // accent 现为 CSS 变量（hsl(var(--chart-N))），不能再字符串拼透明度——
          // 用 color-mix 合成 14% 底（Chrome/Electron 均支持）
          style={{
            background: `color-mix(in srgb, ${accent} 14%, transparent)`,
            color: accent,
          }}
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

function StaleList({
  stale,
  staleDays,
}: {
  stale: StaleItem[];
  staleDays: number;
}) {
  const { t } = useTranslation();
  return (
    <div className="min-w-0 rounded-lg border border-warning/25 bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
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
                <Num className="text-warning">{t("app.daysUnit", { count: s.days })}</Num>
                <span className="text-muted-foreground">{domainLabel("stage", s.当前阶段, t)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}



export default function Dashboard() {
  const { t, i18n } = useTranslation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  // 「按方向 / 按批次」合并后的当前维度（批 4.6）；纯会话态，刷新回默认
  const [dim, setDim] = useState<"direction" | "batch">("direction");

  // 序号守卫：连点两条「顺延 7 天」会触发两次重拉，旧快照可能后到并把刚写成功的
  // 日期回退（2026-09-23 二轮审计）
  const seq = useSeq();
  useEffect(() => {
    const n = seq.next();
    setError(null);
    api
      .dashboard()
      .then((d) => {
        if (seq.isCurrent(n)) setData(d);
      })
      .catch((e: Error) => {
        if (seq.isCurrent(n)) setError(e.message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reloadKey]);

  // 把某条记录的下次动作日期顺延 n 天（仅对"下次动作"类待办开放）
  const snooze = (id: string, date: string) => {
    api
      .updateApplication(id, { 下次动作日期: shiftDate(date, 7) })
      .then(() => setReloadKey((k) => k + 1))
      .catch((e: Error) => setError(e.message));
  };

  if (error) {
    // UX-1：失败也要能自救——统一提示条内嵌重试（重跑同一 effect）
    return <ErrorBanner message={t("dash.loadFailed", { error })} onRetry={() => setReloadKey((k) => k + 1)} />;
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
  // 只画有数据的档位 + 高度随档数（批 4）：demo / 早期工作区常只有 1 档有数据，
  // 固定 200px 会让整卡留出大片空白——高度 = 档数 × 44 + 内边距。
  const visibleScoreByState = scoreByState.filter(
    (t) => t.unapplied + t.active + t.terminal > 0
  );
  const scoreChartHeight = Math.max(120, visibleScoreByState.length * 44 + 24);
  const hasScoreByState = visibleScoreByState.length > 0;
  const hasJobPoolSignal = unappliedHigh.length > 0 || hasScoreByState;

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.dashboard")} />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t("dash.total")}
          value={data.total}
          hint={t("dash.totalHint")}
          icon={<Briefcase size={20} />}
          accent="hsl(var(--chart-1))"
          onClick={() => drillTo({})}
        />
        <StatCard
          label={t("dash.active")}
          value={data.active}
          hint={t("dash.activeHint")}
          icon={<TrendingUp size={20} />}
          accent="hsl(var(--chart-2))"
          onClick={() => drillTo({ active: true })}
        />
        <StatCard
          label={t("dash.upcoming")}
          value={data.upcoming.length}
          hint={t("dash.upcomingHint")}
          icon={<CalendarClock size={20} />}
          accent="hsl(var(--chart-3))"
          onClick={() => drillTo({ dueWithin: 7 })}
        />
        <StatCard
          label={t("dash.overdue")}
          value={data.overdue.length}
          hint={t("dash.overdueHint")}
          icon={<AlertTriangle size={20} />}
          accent="hsl(var(--chart-4))"
          onClick={() => drillTo({ overdue: true })}
        />
      </div>

      {/* 岗位池视角的两块。它们与「有没有投递记录」无关——
          一个岗位都没投过时，高分未投恰恰是最该先看到的东西。 */}
      {hasJobPoolSignal && (
        <div className="space-y-4">
          {unappliedHigh.length > 0 && (
            <div className="rounded-lg border border-primary/30 bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
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
                    <Num className="shrink-0 text-xs">{j.score}</Num>
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
            <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
              <h2
                className="text-sm font-semibold text-foreground"
                title={t("dash.scoreByStateHintFull")}
              >
                {t("dash.scoreByState")}
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t("dash.scoreByStateHint")}
              </p>
              {/* flex-wrap：英文图例三项（Not applied / In progress / Closed）
                  在窄列下换行而不是硬挤（2026-09-17 实测反馈） */}
              <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
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
              <ResponsiveContainer width="100%" height={scoreChartHeight}>
                <BarChart
                  data={visibleScoreByState}
                  layout="vertical"
                  margin={{ left: 8, right: 24 }}
                >
                  <XAxis type="number" hide />
                  {/* 英文档位名（"Strongly recommended" ≈125px）远长于中文，固定
                      84px 会截断/贴柱——按语言给宽（2026-09-17 实测反馈） */}
                  <YAxis
                    type="category"
                    dataKey="tier"
                    width={i18n.language.startsWith("zh") ? 84 : 132}
                    tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(v: string) => domainLabel("tier", v, t)}
                  />
                  <Tooltip
                    cursor={{ fill: "hsl(var(--foreground) / 0.06)" }}
                    contentStyle={{
                      background: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      // 跟 token 与界面字号档走：圆角不再写死 12、字号不再写死
                      // 12px（此前切字号档时提示框不跟着缩放）
                      borderRadius: "var(--radius)",
                      color: "hsl(var(--foreground))",
                      fontSize: "0.75rem",
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
        // 空库不是"出错"，是"还没开始"：给引导，不给错误提示。注意这条分支只在
        // 后端**成功**返回且 total===0 时才会走到（失败走上面的 error 分支）——
        // 把"接口失败"渲染成"欢迎新建工作区"，会让用户以为数据丢了而真去重建。
        <EmptyOnboarding />
      ) : (
        <>
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5 lg:col-span-2">
              <h2 className="mb-4 text-sm font-semibold text-foreground">
                {t("dash.funnelTitle")}
              </h2>
              {/* 纯 DOM 行，不是柱状图：数字要能**右对齐成一列**，与右侧
                  「按方向 / 按批次」同一种读数方式。柱状图的标签只能跟着柱尾走，
                  数据分布一不均就参差不齐（而这一栏的值本来就常常相等）。
                  条形仍按比例，另加一层轨道——数据少时也能看清「占了多少」。 */}
              <BarList
                sortDesc={false}
                max={maxFunnel}
                labelWidth="w-24"
                valueWidth="w-6"
                barHeight="md"
                items={data.funnel.map((f) => ({
                  key: f.stage,
                  label: domainLabel("stage", f.stage, t),
                  value: f.count,
                  color: STAGE_COLORS[f.stage] ?? "hsl(var(--primary))",
                  title: t("dash.funnelRowTitle", {
                    stage: domainLabel("stage", f.stage, t),
                    count: f.count,
                  }),
                  onClick: () => drillTo({ stage: f.stage }),
                }))}
              />
            </div>

            <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
              {/* 一个分段控件合并原来的「按方向 / 按批次」两块（批 4.6）：
                  同一种读数方式（BarList 行）随维度切换，不再两块并列 */}
              <div className="mb-3">
                <Segmented
                  value={dim}
                  onChange={(v) => setDim(v)}
                  ariaLabel={t("dash.dimAria")}
                  options={[
                    { value: "direction", label: t("dash.dimDirection") },
                    { value: "batch", label: t("dash.dimBatch") },
                  ]}
                />
              </div>
              <BarList
                items={
                  dim === "direction"
                    ? data.byDirection.map((d) => ({
                        key: d.key,
                        label: domainLabel("direction", d.key, t),
                        value: d.count,
                        title: t("dash.breakdownRowTitle", {
                          name: domainLabel("direction", d.key, t),
                          count: d.count,
                        }),
                        onClick: () => drillTo({ direction: d.key }),
                      }))
                    : data.byBatch.map((b) => ({
                        key: b.key,
                        label: domainLabel("batch", b.key, t),
                        value: b.count,
                        title: t("dash.breakdownRowTitle", {
                          name: domainLabel("batch", b.key, t),
                          count: b.count,
                        }),
                        onClick: () => drillTo({ batch: b.key }),
                      }))
                }
              />
            </div>
          </div>

          {/* 近 7 天宣讲会（2026-09-18）：投递前的日程——不入主表时间线，
              但「最近有什么活动」是看板上该先看到的信息 */}
          <UpcomingTalks items={data.upcomingTalks ?? []} onOpen={drillToPrepare} />

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">
                {t("dash.upcoming")}
              </h2>
              {data.upcoming.length === 0 ? (
                <EmptyState title={t("dash.upcomingEmpty")} compact />
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

            <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
              <h2 className="mb-3 text-sm font-semibold text-foreground">
                {t("dash.overdueTitle")}
              </h2>
              {data.overdue.length === 0 ? (
                <EmptyState title={t("dash.overdueEmpty")} compact />
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
            <DashboardPendingList
          pending={data.pending}
          onDrill={(id) => drillTo({ sort: "health", focusId: id })}
        />
            <StaleList stale={data.stale} staleDays={data.staleDays} />
          </div>

          {/* 最近动作（批 4）：时间线活动流——与待办同区，填补「页面下部空」 */}
          <ActivityFeed entries={data.recentActivity ?? []} />

          {/* 周期复盘（P3）：转化率 / 停留 / 归因——数据越攒越值钱 */}
          {data.retrospective && (
            <div className="rounded-lg bg-card/40 shadow-card ring-1 ring-highlight/5 p-5">
              <RetrospectivePanel data={data.retrospective} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
