import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import type { TranslationKey } from "../i18n/locales/zh-CN";

// 结果徽章配色：通过=绿、未通过=红、取消=灰、待定=琥珀
const RESULT_VARIANT: Record<string, "success" | "destructive" | "secondary" | "warning"> = {
  通过: "success",
  未通过: "destructive",
  取消: "secondary",
  待定: "warning",
};

// 结果作为**筛选项 label** 时的展示文案（取值仍是 CSV 里的中文）。
// 与 Jobs 页的投递状态筛选取同一口径：筛选项是 UI 文案（翻），记录取值不翻。
const RESULT_LABEL: Record<string, TranslationKey> = {
  待定: "interview.resultTbd",
  通过: "interview.resultPass",
  未通过: "interview.resultFail",
  取消: "interview.resultCancel",
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
  const { t } = useTranslation();
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
              {r ? (RESULT_LABEL[r] ? t(RESULT_LABEL[r]) : r) : t("common.all")}
            </Button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={api.interviewIcsUrl()} title={t("interview.icsTitle")}>
              <Download size={14} /> {t("interview.exportIcs")}
            </a>
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t("interview.add")}
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      <div className="grid grid-cols-12 gap-4">
        {/* 左：列表 */}
        <div className="col-span-5 space-y-2">
          {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条。
              失败时不再同时显示骨架——两张脸同屏比只说失败更糟 */}
          {!loaded && !error ? (
            [0, 1, 2].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)
          ) : loaded && !error && visible.length === 0 ? (
            <Card className="flex flex-col items-center rounded-2xl border-dashed p-8 text-center">
              <CalendarClock size={28} className="mb-3 text-muted-foreground/70" />
              <p className="text-sm text-muted-foreground">{t("interview.emptyTitle")}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground/70">
                {t("interview.emptyHint1")}
                <br />
                {t("interview.emptyHint2")}
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
                      {r.公司 || t("interview.companyMissing")}
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
                      {r.面试时间 || t("interview.timeTbd")}
                    </span>
                    {upcoming && (
                      <span className="text-warning/80">
                        {/* count 选复数形式，hours 是显示值（缺 count 会显示 key 名） */}
                        {hrs < 24
                          ? t("interview.hoursLater", {
                              count: Math.max(1, Math.round(hrs)),
                              hours: Math.max(1, Math.round(hrs)),
                            })
                          : t("interview.inTwoDays")}
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
                    {current.公司} · {current.轮次 || t("interview.fallbackRound")}
                  </h3>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {current.岗位}
                    {current.关联记录 && ` · ${t("interview.related", { value: current.关联记录 })}`}
                    {current.面试时间 && ` · ${current.面试时间}`}
                    {current.面试官 && ` · ${t("interview.interviewer", { value: current.面试官 })}`}
                  </p>
                </div>
                <Select
                  value={current.结果}
                  onValueChange={(v) => quickSetResult(current.面试id, v)}
                >
                  <SelectTrigger className="w-28 shrink-0">
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
                  ["interview.sectionQuestions", current.问题记录],
                  ["interview.sectionAnswers", current.我的回答要点],
                  ["interview.sectionRetro", current.复盘与改进],
                ] as const
              ).map(([labelKey, value]) => (
                <Card key={labelKey} className="rounded-xl p-4">
                  <p className="mb-1.5 text-xs font-medium text-primary">{t(labelKey)}</p>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                    {value || (
                      <span className="text-muted-foreground/70">{t("common.notRecorded")}</span>
                    )}
                  </p>
                </Card>
              ))}
            </Card>
          ) : (
            <Card className="flex h-full min-h-48 items-center justify-center rounded-2xl border-dashed text-xs text-muted-foreground/70">
              {t("interview.selectHint")}
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
