import { useEffect, useState } from "react";
import { ArrowLeft, ChevronDown, FileText, Plus, Sparkles } from "lucide-react";
import { api, type JobDetail, type JobSummary } from "../api";

function levelColor(level: string | null) {
  if (!level) return "bg-slate-500/15 text-slate-400";
  if (level.includes("强烈")) return "bg-good/15 text-good";
  if (level.includes("建议投")) return "bg-accent/15 text-accent";
  if (level.includes("斟酌")) return "bg-warn/15 text-warn";
  return "bg-bad/15 text-bad";
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
    return "bg-bad/15 text-bad border-bad/40";
  return "bg-warn/15 text-warn border-warn/30";
}

// 能力分层标签样式
function levelStyle(level: string | null) {
  if (level === "Primary") return "bg-accent/15 text-accent";
  if (level === "Secondary") return "bg-sky-500/15 text-sky-300";
  if (level === "Weak") return "bg-warn/15 text-warn";
  return "bg-slate-500/15 text-slate-400";
}

export default function Jobs() {
  const [items, setItems] = useState<JobSummary[]>([]);
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [draft, setDraft] = useState({ 公司: "", 岗位: "", JD文本: "" });

  const load = () => {
    api
      .listJobs()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, []);

  const open = (dir: string) => {
    api
      .jobDetail(dir)
      .then(setDetail)
      .catch((e: Error) => setError(e.message));
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
          className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-400 transition-colors hover:text-accent"
        >
          <ArrowLeft size={16} /> 返回岗位池
        </button>

        <h2 className="text-lg font-semibold text-white">{detail.dir}</h2>

        {detail.card?.hardGates &&
          (detail.card.hardGates.items.length > 0 ||
            detail.card.hardGates.conclusion) && (
            <div
              className={`rounded-2xl border p-5 ${gateStyle(
                detail.card.hardGates.conclusion
              )}`}
            >
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-100">
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
                  <span className="text-xs text-bad">
                    原因：{detail.card.hardGates.reason}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                {detail.card.hardGates.items.map((it) => (
                  <span
                    key={it.key}
                    className="rounded-lg border border-white/10 bg-ink-950/60 px-2.5 py-1 text-xs text-slate-300"
                  >
                    {it.key}: {it.value || "—"}
                  </span>
                ))}
              </div>
              {detail.card.hardGates.details.length > 0 && (
                <ul className="mt-3 space-y-1.5 border-t border-white/10 pt-3">
                  {detail.card.hardGates.details.map((d, i) => (
                    <li
                      key={i}
                      className="text-xs leading-relaxed text-slate-400"
                    >
                      {d}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
              <FileText size={16} className="text-accent" /> JD 原文
            </div>
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg bg-ink-950 p-4 text-xs leading-relaxed text-slate-300">
              {detail.jd ?? "（尚未保存 JD）"}
            </pre>
          </div>

          <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
            <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-200">
              <Sparkles size={16} className="text-accent" /> 解析卡
            </div>

            {detail.card ? (
              <div className="space-y-4">
                <div className="flex items-baseline gap-3">
                  <span className="text-3xl font-semibold text-white">
                    {detail.card.total}
                  </span>
                  <span className="text-sm text-slate-500">/ 100</span>
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
                      className="cursor-pointer rounded-xl border border-white/5 bg-ink-950/40 px-3 py-2 transition-colors hover:border-accent/30"
                      onClick={() =>
                        setExpanded(expanded === d.name ? null : d.name)
                      }
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ChevronDown
                            size={14}
                            className={`text-slate-500 transition-transform ${
                              expanded === d.name ? "rotate-180" : ""
                            }`}
                          />
                          <span className="text-xs text-slate-300">
                            {d.name}
                          </span>
                        </div>
                        <span className="font-mono text-xs text-slate-400">
                          {d.score} / {d.max}
                        </span>
                      </div>
                      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/5">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-accent-dim to-accent transition-all duration-700"
                          style={{ width: `${(d.score / d.max) * 100}%` }}
                        />
                      </div>

                      {expanded === d.name && detail.card && (
                        <div className="mt-3 space-y-2 border-t border-white/10 pt-3">
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
                                    <span className="flex-1 text-slate-300">
                                      {h.label}
                                      {h.note && (
                                        <span className="text-slate-500">
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
                                    className="text-xs leading-relaxed text-slate-500"
                                  >
                                    {r}
                                  </li>
                                )
                              )}
                            </ul>
                          )}

                          {!detail.card.dimensionsDetail[d.name] && (
                            <p className="text-xs text-slate-500">
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
              <div className="rounded-lg border border-dashed border-white/15 p-6 text-center">
                <p className="text-sm text-slate-300">尚未生成解析卡</p>
                <p className="mt-2 text-xs leading-relaxed text-slate-500">
                  评分由 AI 在 CodeBuddy 中完成（jd 工作流），写入{" "}
                  <code className="text-slate-400">解析卡.md</code>{" "}
                  后此处会自动展示四维度得分与档位。
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  const inputCls =
    "w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/60 focus:ring-1 focus:ring-accent/30";

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          {error}
        </div>
      )}

      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-400">
          共 {items.length} 个岗位，评分由 AI 完成写入解析卡后展示
        </p>
        <button
          onClick={() => setCreating(true)}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95"
        >
          <Plus size={16} /> 新建岗位
        </button>
      </div>

      {creating && (
        <div className="space-y-3 rounded-2xl border border-accent/30 bg-ink-900/70 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <input
              className={inputCls}
              placeholder="公司名称"
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="岗位名称"
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
          </div>
          <textarea
            className={`${inputCls} min-h-[12rem] resize-y font-mono text-xs leading-relaxed`}
            placeholder="粘贴完整的 JD 原文（含岗位职责与任职要求）。原文会被完整保存，不做改写或摘要。"
            value={draft.JD文本}
            onChange={(e) => setDraft({ ...draft, JD文本: e.target.value })}
          />
          <div className="flex gap-2">
            <button
              onClick={submit}
              disabled={
                !draft.公司.trim() || !draft.岗位.trim() || !draft.JD文本.trim()
              }
              className="cursor-pointer rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              保存岗位
            </button>
            <button
              onClick={() => setCreating(false)}
              className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <p className="text-base font-medium text-slate-200">岗位池还是空的</p>
          <p className="mt-2 text-sm text-slate-400">
            点击「新建岗位」粘贴一份 JD，随后让 AI 生成解析卡，即可看到匹配度评分。
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((job) => (
            <button
              key={job.dir}
              onClick={() => open(job.dir)}
              className="group cursor-pointer rounded-2xl border border-white/10 bg-gradient-to-br from-ink-850 to-ink-900 p-5 text-left transition-all duration-300 hover:-translate-y-1 hover:border-accent/40 hover:shadow-lg hover:shadow-accent/10"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-sm font-semibold leading-snug text-slate-100">
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
                  <span className="text-xs text-slate-500">尚未评分</span>
                )}
                {job.hasJD && (
                  <span className="text-xs text-slate-500">JD 已存</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
