import { useState } from "react";
import { X } from "lucide-react";
import {
  api,
  INTERVIEW_FORMS,
  INTERVIEW_RESULTS,
  INTERVIEW_ROUNDS,
  type Application,
  type Interview,
} from "../api";

const inputCls =
  "w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";
const labelCls = "mb-1 block text-xs font-medium text-slate-400";

export default function InterviewForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (row: Interview) => void;
}) {
  const [apps, setApps] = useState<Application[]>([]);
  const [link, setLink] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [round, setRound] = useState("一面");
  const [when, setWhen] = useState("");
  const [form, setForm] = useState("视频");
  const [interviewer, setInterviewer] = useState("");
  const [questions, setQuestions] = useState("");
  const [answers, setAnswers] = useState("");
  const [retro, setRetro] = useState("");
  const [result, setResult] = useState("待定");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 关联记录下拉按需拉一次：选了岗位自动带出公司名，减少手输
  const loadApps = () => {
    if (apps.length > 0) return;
    api
      .listApplications({})
      .then((r) => setApps(r.items))
      .catch(() => setApps([]));
  };

  const pickApp = (id: string) => {
    setLink(id);
    const hit = apps.find((a) => a.id === id);
    if (hit) {
      setCompany(hit.公司);
      setRole(hit.岗位);
    }
  };

  const submit = () => {
    if (!link && !company.trim()) {
      setError("未关联投递记录时，公司必填");
      return;
    }
    setSaving(true);
    setError(null);
    api
      .createInterview({
        关联记录: link,
        公司: company,
        岗位: role,
        轮次: round,
        // datetime-local 产生 "2026-09-05T14:00"，换成与 CSV 一致的空格分隔
        面试时间: when.replace("T", " "),
        形式: form,
        面试官: interviewer,
        问题记录: questions,
        我的回答要点: answers,
        复盘与改进: retro,
        结果: result,
      })
      .then((row) => onSaved(row))
      .catch((e: Error) => {
        setError(e.message);
        setSaving(false);
      });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
      <div className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-semibold text-white">记录一场面试</h3>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className={labelCls}>关联投递记录（可选）</label>
            <select
              value={link}
              onChange={(e) => pickApp(e.target.value)}
              onFocus={loadApps}
              className={`${inputCls} cursor-pointer`}
            >
              <option value="">不关联（如内推面试）</option>
              {apps.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} · {a.公司} {a.岗位}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className={labelCls}>公司{!link && " *"}（选关联后自动带出）</label>
            <input value={company} onChange={(e) => setCompany(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>岗位</label>
            <input value={role} onChange={(e) => setRole(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>轮次</label>
            <select value={round} onChange={(e) => setRound(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_ROUNDS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>面试时间</label>
            <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>形式</label>
            <select value={form} onChange={(e) => setForm(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_FORMS.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>结果</label>
            <select value={result} onChange={(e) => setResult(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_RESULTS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <label className={labelCls}>面试官</label>
            <input value={interviewer} onChange={(e) => setInterviewer(e.target.value)} className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>问题记录</label>
            <textarea
              value={questions}
              onChange={(e) => setQuestions(e.target.value)}
              rows={3}
              placeholder="被问了什么？按问题逐条记"
              className={`${inputCls} resize-y`}
            />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>我的回答要点</label>
            <textarea
              value={answers}
              onChange={(e) => setAnswers(e.target.value)}
              rows={3}
              placeholder="当时怎么答的？只记要点"
              className={`${inputCls} resize-y`}
            />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>复盘与改进</label>
            <textarea
              value={retro}
              onChange={(e) => setRetro(e.target.value)}
              rows={2}
              placeholder="下次怎么答得更好？复盘是面试记录里唯一能复利的部分"
              className={`${inputCls} resize-y`}
            />
          </div>
        </div>

        {error && <p className="mt-4 text-xs text-bad">{error}</p>}

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-5 py-2 text-sm font-medium text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
