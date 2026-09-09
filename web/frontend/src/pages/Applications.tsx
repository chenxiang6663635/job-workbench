import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  ChevronsUpDown,
  FileUp,
  Inbox,
  Plus,
  Search,
  X,
} from "lucide-react";
import {
  api,
  BATCHES,
  STAGES,
  TERMINAL,
  type Application,
  type HistoryEntry,
} from "../api";
import ImportApplicationsDialog from "../components/ImportApplicationsDialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";

const DIRECTIONS = ["datacenter", "hvac", "other"];

// Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达
const ALL = "__all__";

// 静默阈值与后端 tracker.STALE_DAYS 一致；停留超过该值高亮
const STALE_DAYS = 14;

type SortKey = "next" | "score" | "stale" | "health";

// 健康度四态：颜色即严重度，具体理由放在 hover 的 title 里（给理由不给黑箱分数）
const HEALTH_META: Record<string, { label: string; cls: string }> = {
  urgent: { label: "紧急", cls: "bg-bad/15 text-bad" },
  overdue: { label: "逾期", cls: "bg-warn/15 text-warn" },
  stale: { label: "停滞", cls: "bg-accent/15 text-accent" },
  ok: { label: "正常", cls: "bg-white/5 text-slate-400" },
};

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

// 页面初始状态：若来自看板下钻则读 sessionStorage，否则全空
function readDrill(): Drill {
  try {
    const raw = sessionStorage.getItem("jobws_drill");
    if (!raw) return {};
    return JSON.parse(raw) as Drill;
  } catch {
    return {};
  }
}

function stageStyle(stage: string) {
  if (stage === "已挂") return "bg-bad/15 text-bad";
  if (stage === "已放弃") return "bg-slate-500/15 text-slate-400";
  // 我拒绝的 offer 是双向选择，不是失败——用中性偏绿，区别于失败红
  if (stage === "我拒绝的 offer") return "bg-good/10 text-good/80";
  if (stage === "offer" || stage === "签约")
    return "bg-good/15 text-good";
  return "bg-accent/15 text-accent";
}

const SORT_LABELS: Record<SortKey, string> = {
  next: "下次动作日期",
  score: "评分",
  stale: "停留",
  health: "健康度",
};

function HistoryTimeline({ entries }: { entries: HistoryEntry[] }) {
  if (entries.length === 0) {
    return <p className="text-xs text-slate-500">该记录暂无变更记录。</p>;
  }
  return (
    <div className="space-y-0">
      {entries.map((e, i) => {
        const isStage = e.字段 === "当前阶段" || e.字段 === "创建";
        return (
          <div key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                  isStage ? "bg-accent" : "bg-slate-600"
                }`}
              />
              {i !== entries.length - 1 && (
                <span className="w-px flex-1 bg-white/5" />
              )}
            </div>
            <div className="pb-3">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-slate-400">{e.时间}</span>
                <span className="rounded bg-white/5 px-1.5 py-0.5 text-[10px] text-slate-400">
                  {e.字段}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-300">
                <span className="text-slate-500">{e.原值 || "（空）"}</span>
                <span className="mx-1 text-slate-600">→</span>
                {e.新值 || "（空）"}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function Applications() {
  const drill = useMemo(readDrill, []);
  const [items, setItems] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState({
    stage: drill.stage ?? "",
    direction: drill.direction ?? "",
    batch: drill.batch ?? "",
    q: "",
  });
  const [sort, setSort] = useState<SortKey>(drill.sort ?? "next");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showImport, setShowImport] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [timelines, setTimelines] = useState<Record<string, HistoryEntry[]>>({});
  const [draft, setDraft] = useState({
    公司: "",
    岗位: "",
    方向: "hvac",
    批次: "正式批",
    评分: 60,
    截止日期: "",
    当前阶段: "待投",
  });

  const load = () => {
    setLoading(true);
    api
      .listApplications({ ...filter, sort })
      .then(
        (r) => {
          setItems(r.items);
          // 若下钻带 focusId，自动展开并滚动到该行
          if (drill.focusId) {
            setExpanded((prev) => ({ ...prev, [drill.focusId!]: true }));
          }
        },
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  };

  useEffect(load, [filter, sort]);
  // 下钻筛选只生效一次：首次加载后清掉，避免重复返回看板时的旧筛选残留
  useEffect(() => {
    sessionStorage.removeItem("jobws_drill");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const patch = (id: string, body: Partial<Application>) => {
    api
      .updateApplication(id, body)
      .then(() => load())
      .catch((e: Error) => setError(e.message));
  };

  const submit = () => {
    api
      .addApplication({ ...draft, 评分: String(draft.评分) })
      .then(() => {
        setCreating(false);
        setDraft({
          公司: "",
          岗位: "",
          方向: "hvac",
          批次: "正式批",
          评分: 60,
          截止日期: "",
          当前阶段: "待投",
        });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  const toggleTimeline = (id: string) => {
    const next = { ...expanded, [id]: !expanded[id] };
    setExpanded(next);
    if (next[id] && !timelines[id]) {
      api
        .applicationHistory(id)
        .then((h) => setTimelines((prev) => ({ ...prev, [id]: h.items })))
        .catch((e: Error) => setError(e.message));
    }
  };

  const sortBtn = (key: SortKey) => {
    const active = sort === key;
    return (
      <button
        onClick={() => setSort(active ? "next" : key)}
        className={`flex cursor-pointer items-center gap-1 font-medium transition-colors ${
          active ? "text-accent" : "text-slate-400 hover:text-slate-200"
        }`}
        title={`按${SORT_LABELS[key]}排序`}
      >
        {SORT_LABELS[key]}
        <ChevronsUpDown size={12} className={active ? "opacity-100" : "opacity-40"} />
      </button>
    );
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-center justify-between rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-56">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            placeholder="搜索公司、岗位或备注…"
            className="pl-8"
          />
        </div>

        {/* Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达 */}
        <Select
          value={filter.stage || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, stage: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="全部阶段" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部阶段</SelectItem>
            {STAGES.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filter.direction || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, direction: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="全部方向" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部方向</SelectItem>
            {DIRECTIONS.map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filter.batch || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, batch: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="全部批次" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>全部批次</SelectItem>
            {BATCHES.map((b) => (
              <SelectItem key={b} value={b}>
                {b}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button variant="outline" onClick={() => setShowImport(true)}>
          <FileUp size={15} /> 批量导入
        </Button>

        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> 新增投递
        </Button>
      </div>

      {showImport && (
        <ImportApplicationsDialog
          onClose={() => setShowImport(false)}
          onImported={load}
        />
      )}

      {creating && (
        <div className="rounded-2xl border border-primary/30 bg-card/70 shadow-card ring-1 ring-white/5 p-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Input
              placeholder="公司名称"
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <Input
              placeholder="岗位名称"
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
            <Select
              value={draft.方向}
              onValueChange={(v) => setDraft({ ...draft, 方向: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="方向" />
              </SelectTrigger>
              <SelectContent>
                {DIRECTIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={draft.批次}
              onValueChange={(v) => setDraft({ ...draft, 批次: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="批次" />
              </SelectTrigger>
              <SelectContent>
                {BATCHES.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              type="date"
              value={draft.截止日期}
              onChange={(e) => setDraft({ ...draft, 截止日期: e.target.value })}
            />
            <Input
              type="number"
              min={0}
              max={100}
              value={draft.评分}
              onChange={(e) =>
                setDraft({ ...draft, 评分: Number(e.target.value) })
              }
            />
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              onClick={submit}
              disabled={!draft.公司.trim() || !draft.岗位.trim()}
            >
              保存
            </Button>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-2 rounded-2xl border border-border p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium">没有匹配的投递记录</p>
          <p className="text-sm text-muted-foreground">
            调整筛选条件，或点击右上角「新增投递」记录第一家公司。
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-secondary text-xs uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">公司 / 岗位</th>
                <th className="px-4 py-3 text-left font-medium">方向</th>
                <th className="px-4 py-3 text-left font-medium">批次</th>
                <th className="px-4 py-3 text-left font-medium">当前阶段</th>
                <th className="px-4 py-3 text-left font-medium">状态原因</th>
                <th className="px-4 py-3 text-left font-medium">
                  <span className="inline-flex items-center gap-1">
                    {sortBtn("next")}
                  </span>
                </th>
                <th className="px-4 py-3 text-left font-medium">截止</th>
                <th className="px-4 py-3 text-left font-medium">
                  <span className="inline-flex items-center gap-1">
                    {sortBtn("score")}
                  </span>
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  <span className="inline-flex items-center gap-1">
                    {sortBtn("stale")}
                  </span>
                </th>
                <th className="px-4 py-3 text-left font-medium">
                  <span className="inline-flex items-center gap-1">
                    {sortBtn("health")}
                  </span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((it) => {
                const isExpanded = expanded[it.id];
                const staleDays = typeof it.stageDays === "number" ? it.stageDays : null;
                const isStale = staleDays !== null && staleDays >= STALE_DAYS;
                return (
                  <Fragment key={it.id}>
                    <tr
                      id={`row-${it.id}`}
                      className="group bg-card/40 shadow-card ring-1 ring-white/5 transition-colors hover:bg-secondary"
                    >
                      <td className="border-l-2 border-transparent px-4 py-3 transition-colors group-hover:border-primary">
                        <button
                          onClick={() => toggleTimeline(it.id)}
                          className="mr-2 inline-flex cursor-pointer align-middle text-muted-foreground transition-colors hover:text-primary"
                          title={isExpanded ? "收起时间线" : "展开时间线"}
                        >
                          {isExpanded ? (
                            <ChevronDown size={14} />
                          ) : (
                            <ChevronRight size={14} />
                          )}
                        </button>
                        <span className="font-medium text-slate-100">
                          {it.公司 || "—"}
                        </span>
                        <div className="pl-6 text-xs text-slate-500">
                          {it.岗位 || "未填岗位"}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-slate-300">{it.方向 || "—"}</td>
                      <td className="px-4 py-3 text-slate-300">{it.批次 || "—"}</td>
                      <td className="px-4 py-3">
                        {TERMINAL.includes(it.当前阶段) ? (
                          <div className="flex flex-col gap-0.5">
                            <span
                              className={`rounded-md px-2 py-1 text-xs font-medium ${stageStyle(
                                it.当前阶段
                              )}`}
                            >
                              {it.当前阶段}
                            </span>
                            <span className="text-[10px] text-slate-500">
                              已终态，不可改阶段
                            </span>
                          </div>
                        ) : (
                          <select
                            value={it.当前阶段}
                            onChange={(e) =>
                              patch(it.id, { 当前阶段: e.target.value })
                            }
                            className={`cursor-pointer rounded-md border-0 px-2 py-1 text-xs font-medium outline-none ${stageStyle(
                              it.当前阶段
                            )}`}
                          >
                            {STAGES.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <input
                          defaultValue={it.状态原因}
                          onBlur={(e) => {
                            if (e.target.value !== it.状态原因) {
                              patch(it.id, { 状态原因: e.target.value });
                            }
                          }}
                          placeholder={
                            TERMINAL.includes(it.当前阶段) ? "必填原因" : "选填"
                          }
                          className="w-full min-w-[8rem] rounded border border-transparent bg-transparent px-2 py-1 text-xs text-slate-200 outline-none transition-colors placeholder:text-slate-600 hover:border-white/10 focus:border-accent/50"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          defaultValue={it.下次动作日期}
                          onBlur={(e) => {
                            if (e.target.value !== it.下次动作日期) {
                              patch(it.id, { 下次动作日期: e.target.value });
                            }
                          }}
                          type="date"
                          title="下次动作日期"
                          className="w-36 rounded border border-transparent bg-transparent px-2 py-1 font-mono text-xs text-slate-300 outline-none transition-colors hover:border-white/10 focus:border-accent/50"
                        />
                        <div className="pl-2 text-xs text-slate-500">
                          {it.下次动作 || "—"}
                        </div>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">
                        {it.截止日期 || "—"}
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs text-accent">
                          {it.评分 || "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {staleDays !== null ? (
                          <span
                            className={`inline-flex items-center gap-1 font-mono text-xs ${
                              isStale ? "text-warn" : "text-slate-400"
                            }`}
                          >
                            {isStale && (
                              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
                            )}
                            {staleDays} 天
                          </span>
                        ) : (
                          <span className="text-xs text-slate-600">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {(() => {
                          const h = it.health;
                          if (!h || !h.level) {
                            return <span className="text-xs text-slate-600">—</span>;
                          }
                          const meta = HEALTH_META[h.level];
                          return (
                            <span
                              title={h.reasons.join("；") || "暂无异常"}
                              className={`cursor-help rounded-md px-2 py-1 text-xs font-medium ${meta.cls}`}
                            >
                              {meta.label}
                            </span>
                          );
                        })()}
                      </td>
                    </tr>
                    {isExpanded && (
                      <tr className="bg-background/60">
                        <td
                          colSpan={10}
                          className="border-l-2 border-accent/30 px-6 py-4"
                        >
                          <HistoryTimeline entries={timelines[it.id] ?? []} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
