import { useEffect, useMemo, useState } from "react";
import { CalendarClock, CalendarPlus, Download, Plus } from "lucide-react";
import {
  api,
  INTERVIEW_RESULTS,
  type Interview,
} from "../api";
import InterviewForm from "./InterviewForm";

// 结果徽章配色：通过=绿、未通过=红、取消=灰、待定=琥珀
const RESULT_CLS: Record<string, string> = {
  通过: "bg-good/15 text-good border-good/30",
  未通过: "bg-bad/15 text-bad border-bad/30",
  取消: "bg-white/5 text-slate-500 border-white/10",
  待定: "bg-warn/15 text-warn border-warn/30",
};

function ResultBadge({ value }: { value: string }) {
  return (
    <span
      className={`rounded-md border px-1.5 py-0.5 text-[11px] ${
        RESULT_CLS[value] ?? RESULT_CLS["待定"]
      }`}
    >
      {value}
    </span>
  );
}

// 距面试的小时数；过去返回负数。空时间返回 null
function hoursUntil(when: string): number | null {
  if (!when) return null;
  const t = new Date(when.replace(" ", "T")).getTime();
  if (Number.isNaN(t)) return null;
  return (t - Date.now()) / 3600_000;
}

export default function InterviewList() {
  const [rows, setRows] = useState<Interview[]>([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = () => {
    api
      .listInterviews()
      .then((r) => {
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(reload, []);

  const visible = useMemo(
    () => (filter ? rows.filter((r) => r.结果 === filter) : rows),
    [rows, filter]
  );

  const current = rows.find((r) => r.面试id === selected) ?? null;

  // 快捷更新结果：列表右侧详情里的下拉，改完即存
  const quickSetResult = (id: string, value: string) => {
    api
      .updateInterview(id, { 结果: value })
      .then(() => reload())
      .catch((e: Error) => setError(e.message));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1">
          {["", ...INTERVIEW_RESULTS].map((r) => (
            <button
              key={r || "all"}
              onClick={() => setFilter(r)}
              className={`cursor-pointer rounded-full px-3 py-1.5 text-xs transition-colors ${
                filter === r
                  ? "bg-accent/15 text-accent"
                  : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
              }`}
            >
              {r || "全部"}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <a
            href={api.interviewIcsUrl()}
            title="把面试日程导入手机/电脑日历，提前 1 小时提醒"
            className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 transition-colors hover:border-accent/40 hover:text-accent"
          >
            <Download size={14} /> 导出日程 .ics
          </a>
          <button
            onClick={() => setShowForm(true)}
            className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-gradient-to-r from-accent to-accent-dim px-3.5 py-2 text-xs font-medium text-white transition-all hover:opacity-90"
          >
            <Plus size={14} /> 记录面试
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-xs text-bad">
          {error}
        </div>
      )}

      <div className="grid grid-cols-12 gap-4">
        {/* 左：列表 */}
        <div className="col-span-5 space-y-2">
          {loaded && visible.length === 0 && (
            <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-8 text-center">
              <CalendarClock size={28} className="mx-auto mb-3 text-slate-600" />
              <p className="text-sm text-slate-400">还没有面试记录</p>
              <p className="mt-1 text-xs leading-relaxed text-slate-600">
                每一场面试都值得记下来——问题、回答、复盘，
                <br />
                复盘是唯一能复利的部分
              </p>
            </div>
          )}
          {visible.map((r) => {
            const hrs = hoursUntil(r.面试时间);
            const upcoming = hrs !== null && hrs > 0 && hrs < 48 && r.结果 === "待定";
            return (
              <button
                key={r.面试id}
                onClick={() => setSelected(r.面试id)}
                className={`w-full cursor-pointer rounded-xl border p-3.5 text-left transition-all duration-200 hover:-translate-y-0.5 ${
                  selected === r.面试id
                    ? "border-accent/50 bg-accent/10"
                    : "border-white/10 bg-ink-900/60 hover:border-white/20"
                } ${upcoming ? "ring-1 ring-warn/40" : ""}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium text-slate-100">
                    {r.公司 || "（未填公司）"}
                  </span>
                  <ResultBadge value={r.结果} />
                </div>
                <div className="mt-1 truncate text-xs text-slate-500">
                  {r.岗位}
                  {r.轮次 && ` · ${r.轮次}`}
                  {r.形式 && ` · ${r.形式}`}
                </div>
                <div className="mt-1.5 flex items-center gap-1.5 text-xs">
                  <CalendarClock size={12} className={upcoming ? "text-warn" : "text-slate-600"} />
                  <span className={upcoming ? "text-warn" : "text-slate-500"}>
                    {r.面试时间 || "时间待定"}
                  </span>
                  {upcoming && (
                    <span className="text-warn/80">
                      {hrs < 24 ? `· ${Math.max(1, Math.round(hrs))} 小时后` : "· 明后两天"}
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>

        {/* 右：详情（三段式：问题 / 回答 / 复盘） */}
        <div className="col-span-7">
          {current ? (
            <div className="space-y-4 rounded-2xl border border-white/10 bg-ink-900/60 p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-white">
                    {current.公司} · {current.轮次 || "面试"}
                  </h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {current.岗位}
                    {current.关联记录 && ` · 关联 ${current.关联记录}`}
                    {current.面试时间 && ` · ${current.面试时间}`}
                    {current.面试官 && ` · 面试官 ${current.面试官}`}
                  </p>
                </div>
                <select
                  value={current.结果}
                  onChange={(e) => quickSetResult(current.面试id, e.target.value)}
                  className="cursor-pointer rounded-lg border border-white/10 bg-ink-950/60 px-2 py-1.5 text-xs text-slate-200 outline-none focus:border-accent/50"
                >
                  {INTERVIEW_RESULTS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </div>

              {(
                [
                  ["问题记录", current.问题记录],
                  ["我的回答要点", current.我的回答要点],
                  ["复盘与改进", current.复盘与改进],
                ] as const
              ).map(([label, value]) => (
                <div key={label} className="rounded-xl border border-white/5 bg-ink-950/40 p-4">
                  <p className="mb-1.5 text-xs font-medium text-accent/80">{label}</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">
                    {value || <span className="text-slate-600">（未记录）</span>}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex h-full min-h-48 items-center justify-center rounded-2xl border border-dashed border-white/10 text-xs text-slate-600">
              从左侧选择一场面试查看记录
            </div>
          )}
        </div>
      </div>

      {showForm && (
        <InterviewForm
          onClose={() => setShowForm(false)}
          onSaved={(row) => {
            setShowForm(false);
            setSelected(row.面试id);
            reload();
          }}
        />
      )}
    </div>
  );
}
