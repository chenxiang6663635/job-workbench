import { useEffect, useMemo, useState } from "react";
import { CalendarClock, Download, Plus } from "lucide-react";
import {
  api,
  INTERVIEW_RESULTS,
  type Interview,
} from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import InterviewForm from "./InterviewForm";

// 结果徽章配色：通过=绿、未通过=红、取消=灰、待定=琥珀
const RESULT_VARIANT: Record<string, "success" | "destructive" | "secondary" | "warning"> = {
  通过: "success",
  未通过: "destructive",
  取消: "secondary",
  待定: "warning",
};

function ResultBadge({ value }: { value: string }) {
  return (
    <Badge
      variant={RESULT_VARIANT[value] ?? "warning"}
      className="rounded-md px-1.5 py-0 text-[11px]"
    >
      {value}
    </Badge>
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
            <Button
              key={r || "all"}
              variant={filter === r ? "secondary" : "ghost"}
              size="sm"
              onClick={() => setFilter(r)}
              className={`rounded-full ${filter === r ? "text-primary" : "text-muted-foreground"}`}
            >
              {r || "全部"}
            </Button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={api.interviewIcsUrl()} title="把面试日程导入手机/电脑日历，提前 1 小时提醒">
              <Download size={14} /> 导出日程 .ics
            </a>
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <Plus size={14} /> 记录面试
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      <div className="grid grid-cols-12 gap-4">
        {/* 左：列表 */}
        <div className="col-span-5 space-y-2">
          {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条 */}
          {!loaded ? (
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)
          ) : visible.length === 0 ? (
            <Card className="flex flex-col items-center rounded-2xl border-dashed p-8 text-center">
              <CalendarClock size={28} className="mb-3 text-muted-foreground/70" />
              <p className="text-sm text-muted-foreground">还没有面试记录</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground/70">
                每一场面试都值得记下来——问题、回答、复盘，
                <br />
                复盘是唯一能复利的部分
              </p>
            </Card>
          ) : null}
          {visible.map((r) => {
            const hrs = hoursUntil(r.面试时间);
            const upcoming = hrs !== null && hrs > 0 && hrs < 48 && r.结果 === "待定";
            const active = selected === r.面试id;
            return (
              <Card
                key={r.面试id}
                className={`rounded-xl transition-all duration-200 hover:-translate-y-0.5 ${
                  active ? "border-primary/50 bg-primary/10" : "hover:border-border-strong"
                } ${upcoming ? "ring-1 ring-warning/40" : ""}`}
              >
                <button
                  type="button"
                  onClick={() => setSelected(r.面试id)}
                  className="w-full cursor-pointer p-3.5 text-left"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm font-medium text-foreground">
                      {r.公司 || "（未填公司）"}
                    </span>
                    <ResultBadge value={r.结果} />
                  </div>
                  <div className="mt-1 truncate text-xs text-muted-foreground">
                    {r.岗位}
                    {r.轮次 && ` · ${r.轮次}`}
                    {r.形式 && ` · ${r.形式}`}
                  </div>
                  <div className="mt-1.5 flex items-center gap-1.5 text-xs">
                    <CalendarClock
                      size={12}
                      className={upcoming ? "text-warning" : "text-muted-foreground/70"}
                    />
                    <span className={upcoming ? "text-warning" : "text-muted-foreground"}>
                      {r.面试时间 || "时间待定"}
                    </span>
                    {upcoming && (
                      <span className="text-warning/80">
                        {hrs < 24 ? `· ${Math.max(1, Math.round(hrs))} 小时后` : "· 明后两天"}
                      </span>
                    )}
                  </div>
                </button>
              </Card>
            );
          })}
        </div>

        {/* 右：详情（三段式：问题 / 回答 / 复盘） */}
        <div className="col-span-7">
          {current ? (
            <Card className="space-y-4 rounded-2xl p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-base font-semibold text-foreground">
                    {current.公司} · {current.轮次 || "面试"}
                  </h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {current.岗位}
                    {current.关联记录 && ` · 关联 ${current.关联记录}`}
                    {current.面试时间 && ` · ${current.面试时间}`}
                    {current.面试官 && ` · 面试官 ${current.面试官}`}
                  </p>
                </div>
                <Select
                  value={current.结果}
                  onValueChange={(v) => quickSetResult(current.面试id, v)}
                >
                  <SelectTrigger className="w-24 shrink-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {INTERVIEW_RESULTS.map((r) => (
                      <SelectItem key={r} value={r}>
                        {r}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {(
                [
                  ["问题记录", current.问题记录],
                  ["我的回答要点", current.我的回答要点],
                  ["复盘与改进", current.复盘与改进],
                ] as const
              ).map(([label, value]) => (
                <Card key={label} className="rounded-xl p-4">
                  <p className="mb-1.5 text-xs font-medium text-primary">{label}</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {value || <span className="text-muted-foreground/70">（未记录）</span>}
                  </p>
                </Card>
              ))}
            </Card>
          ) : (
            <Card className="flex h-full min-h-48 items-center justify-center rounded-2xl border-dashed text-xs text-muted-foreground/70">
              从左侧选择一场面试查看记录
            </Card>
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
