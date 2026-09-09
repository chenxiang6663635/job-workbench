import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  FileText,
  Inbox,
  Link2,
  Loader2,
  Plus,
  Sparkles,
} from "lucide-react";
import GapPanel from "../components/GapPanel";
import { api, type JobDetail, type JobSummary } from "../api";
import { Button } from "../components/ui/button";
import { Input, Textarea } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";

function levelColor(level: string | null) {
  if (!level) return "bg-secondary text-muted-foreground";
  if (level.includes("强烈")) return "bg-good/15 text-good";
  if (level.includes("建议投")) return "bg-accent/15 text-accent";
  if (level.includes("斟酌")) return "bg-warn/15 text-warn";
  return "bg-destructive/15 text-destructive";
}

// 证据标签徽章颜色：精确=蓝、模糊=琥珀、语义=青
function evidenceStyle(ev: string | null) {
  if (ev === "精确") return "bg-sky-500/15 text-sky-300 border-sky-400/30";
  if (ev === "模糊") return "bg-warn/15 text-warn border-warn/30";
  if (ev === "语义") return "bg-teal-500/15 text-teal-300 border-teal-400/30";
  return "";
}

// 硬门槛三态样式
function gateStyle(conclusion: string | null) {
  if (conclusion === "通过") return "bg-good/15 text-good border-good/30";
  if (conclusion === "不通过")
    return "bg-destructive/15 text-destructive border-destructive/40";
  return "bg-warn/15 text-warn border-warn/30";
}

// 能力分层标签样式
function levelStyle(level: string | null) {
  if (level === "Primary") return "bg-accent/15 text-accent";
  if (level === "Secondary") return "bg-sky-500/15 text-sky-300";
  if (level === "Weak") return "bg-warn/15 text-warn";
  return "bg-secondary text-muted-foreground";
}

export default function Jobs() {
  const [items, setItems] = useState<JobSummary[]>([]);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [draft, setDraft] = useState({ 公司: "", 岗位: "", JD文本: "" });
  // JD 链接抓取（第三批）：尽力而为，失败即明确降级提示手动粘贴
  const [jdUrl, setJdUrl] = useState("");
  const [fetching, setFetching] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .listJobs()
      .then(
        (r) => setItems(r.items),
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  };

  useEffect(load, []);

  const open = (dir: string) => {
    api
      .jobDetail(dir)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
  };

  // 抓取成功后后端已写入 JD原文.md，直接打开详情让用户核对原文——
  // 抓取只是省掉复制粘贴，内容仍必须由用户过目（不做任何改写或摘要）
  const fetchJd = () => {
    if (!draft.公司.trim() || !draft.岗位.trim()) {
      setError("抓取前先填公司与岗位（决定 JD 存在哪个岗位目录）");
      return;
    }
    setFetching(true);
    setError(null);
    api
      .fetchJd({ url: jdUrl.trim(), 公司: draft.公司.trim(), 岗位: draft.岗位.trim() })
      .then((r) => {
        setFetching(false);
        setCreating(false);
        setJdUrl("");
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
        open(r.dir);
      })
      .catch((e: Error) => {
        setError(e.message);
        setFetching(false);
      });
  };

  const submit = () => {
    api
      .createJob(draft)
      .then(() => {
        setCreating(false);
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  if (detail) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => setDetail(null)}
          className="flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-accent"
        >
          <ArrowLeft size={16} /> 返回岗位池
        </button>

        <h2 className="text-lg font-semibold text-foreground">{detail.dir}</h2>

        {detail.card?.hardGates &&
          (detail.card.hardGates.items.length > 0 ||
            detail.card.hardGates.conclusion) && (
            <div
              className={`rounded-lg border p-5 ${gateStyle(
                detail.card.hardGates.conclusion
              )}`}
            >
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-foreground">
                  资格硬门槛
                </span>
                <span
                  className={`rounded-full border px-3 py-0.5 text-xs font-semibold ${gateStyle(
                    detail.card.hardGates.conclusion
                  )}`}
                >
                  {detail.card.hardGates.conclusion ?? "待确认"}
                </span>
                {detail.card.hardGates.reason && (
                  <span className="text-xs text-destructive">
                    原因：{detail.card.hardGates.reason}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {detail.card.hardGates.items.map((it) => (
                  <span
                    key={it.key}
                    className="rounded-lg border border-border bg-background/60 px-2.5 py-1 text-xs text-muted-foreground"
                  >
                    {it.key}: {it.value || "—"}
                  </span>
                ))}
              </div>
              {detail.card.hardGates.details.length > 0 && (
                <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
                  {detail.card.hardGates.details.map((d, i) => (
                    <li
                      key={i}
                      className="text-xs leading-relaxed text-muted-foreground"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <FileText size={16} className="text-accent" /> JD 原文
            </div>
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-4 text-xs leading-relaxed text-muted-foreground">
              {detail.jd ?? "（尚未保存 JD）"}
            </pre>
          </div>

          <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
              <Sparkles size={16} className="text-accent" /> 解析卡
            </div>

            {detail.card ? (
              <div className="space-y-4">
                <div className="flex items-baseline gap-3">
                  <span className="text-3xl font-semibold text-foreground">
                    {detail.card.total}
                  </span>
                  <span className="text-sm text-muted-foreground">/ 100</span>
                  <span
                    className={`ml-auto rounded-full px-3 py-1 text-xs font-medium ${levelColor(
                      detail.card.level
                    )}`}
                  >
                    {detail.card.level}
                  </span>
                </div>

                <div className="space-y-2">
                  {detail.card.dimensions.map((d) => (
                    <div
                      key={d.name}
                      className="cursor-pointer rounded-xl border border-border/60 bg-background/40 px-3 py-2 transition-colors hover:border-accent/30"
                      onClick={() =>
                        setExpanded(expanded === d.name ? null : d.name)
                      }
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ChevronDown
                            size={14}
                            className={`text-muted-foreground transition-transform ${
                              expanded === d.name ? "rotate-180" : ""
                            }`}
                          />
                          <span className="text-xs text-muted-foreground">
                            {d.name}
                          </span>
                        </div>
                        <span className="font-mono text-xs text-muted-foreground">
                          {d.score} / {d.max}
                        </span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary/60">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-accent-dim to-accent transition-all duration-700"
                          style={{ width: `${(d.score / d.max) * 100}%` }}
                        />
                      </div>

                      {expanded === d.name && detail.card && (
                        <div className="mt-3 space-y-2 border-t border-border pt-3">
                          {/* 词典命中列表（带证据标签） */}
                          {(detail.card.dimensionsDetail[d.name]?.hits ?? [])
                            .length > 0 && (
                            <ul className="space-y-1.5">
                              {detail.card.dimensionsDetail[d.name].hits.map(
                                (h, i) => (
                                  <li
                                    key={i}
                                    className="flex items-start gap-2 text-xs"
                                  >
                                    <span
                                      className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${levelStyle(
                                        h.level
                                      )}`}
                                    >
                                      {h.level ?? "明细"}
                                    </span>
                                    <span className="flex-1 text-muted-foreground">
                                      {h.label}
                                      {h.note && (
                                        <span className="text-muted-foreground">
                                          {" "}
                                          — {h.note}
                                        </span>
                                      )}
                                    </span>
                                    {h.evidence && (
                                      <span
                                        className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-medium ${evidenceStyle(
                                          h.evidence
                                        )}`}
                                      >
                                        {h.evidence}
                                      </span>
                                    )}
                                  </li>
                                )
                              )}
                            </ul>
                          )}

                          {/* 该维度的逐条说明原文 */}
                          {(detail.card.dimensionsDetail[d.name]?.raw ?? [])
                            .length > 0 && (
                            <ul className="space-y-1.5">
                              {detail.card.dimensionsDetail[d.name].raw.map(
                                (r, i) => (
                                  <li
                                    key={i}
                                    className="text-xs leading-relaxed text-muted-foreground"
                                  >
                                    {r}
                                  </li>
                                )
                              )}
                            </ul>
                          )}

                          {!detail.card.dimensionsDetail[d.name] && (
                            <p className="text-xs text-muted-foreground">
                              暂无该维度的逐条依据
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {detail.card.action && (
                  <p className="rounded-lg bg-accent/10 px-3 py-2 text-xs text-accent-soft">
                    下一步：{detail.card.action}
                  </p>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-border p-6 text-center">
                <p className="text-sm text-muted-foreground">尚未生成解析卡</p>
                <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                  评分由 AI 在 CodeBuddy 中完成（jd 工作流），写入{" "}
                  <code className="text-muted-foreground">解析卡.md</code>{" "}
                  后此处会自动展示四维度得分与档位。
                </p>
              </div>
            )}

            {/* JD↔简历差距清单：只依赖 JD，未评分的岗位也能看——
                往往正是"还没评分但想先知道差在哪"的时刻 */}
            <div className="rounded-xl border border-border bg-background/40 p-4">
              <GapPanel dir={detail.dir} />
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          共 {items.length} 个岗位，评分由 AI 完成写入解析卡后展示
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> 新建岗位
        </Button>
      </div>

      {creating && (
        <div className="space-y-3 rounded-lg border border-accent/30 bg-card/70 shadow-card ring-1 ring-white/5 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
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
          </div>
          {/* JD 链接抓取：省掉复制粘贴，但抓不到会直说，不假装成功 */}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="flex-1"
              placeholder="JD 网页链接（选填）：https://… 抓取成功后自动存为 JD原文.md"
              value={jdUrl}
              onChange={(e) => setJdUrl(e.target.value)}
            />
            <Button
              variant="outline"
              onClick={fetchJd}
              disabled={
                fetching || !jdUrl.trim() || !draft.公司.trim() || !draft.岗位.trim()
              }
              title={!draft.公司.trim() || !draft.岗位.trim() ? "先填公司与岗位" : "抓取网页正文"}
            >
              {fetching ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
              {fetching ? "抓取中…" : "从链接抓取"}
            </Button>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground/70">
            只取网页正文，不做改写或摘要。需登录、有反爬或纯 JS 渲染的页面抓不到，
            会明确提示你手动粘贴——不会把半截内容当成抓取成功。
          </p>
          <Textarea
            className="min-h-[12rem] resize-y font-mono text-xs leading-relaxed"
            placeholder="粘贴完整的 JD 原文（含岗位职责与任职要求）。原文会被完整保存，不做改写或摘要。"
            value={draft.JD文本}
            onChange={(e) => setDraft({ ...draft, JD文本: e.target.value })}
          />
          <div className="flex gap-2">
            <Button
              onClick={submit}
              disabled={
                !draft.公司.trim() || !draft.岗位.trim() || !draft.JD文本.trim()
              }
            >
              保存岗位
            </Button>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium text-foreground">岗位池还是空的</p>
          <p className="mt-2 text-sm text-muted-foreground">
            点击「新建岗位」粘贴一份 JD，随后让 AI 生成解析卡，即可看到匹配度评分。
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((job) => (
            <button
              key={job.dir}
              onClick={() => open(job.dir)}
              className="group cursor-pointer rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5 text-left transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg hover:shadow-accent/10"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold leading-snug text-foreground">
                  {job.dir}
                </h3>
                {job.score !== null && (
                  <span className="font-mono text-lg font-semibold text-accent">
                    {job.score}
                  </span>
                )}
              </div>
              <div className="mt-3 flex items-center gap-2">
                {job.level ? (
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${levelColor(
                      job.level
                    )}`}
                  >
                    {job.level}
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">尚未评分</span>
                )}
                {job.hasJD && (
                  <span className="text-xs text-muted-foreground">JD 已存</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
