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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";

const inputCls =
  "w-full rounded-lg border border-border bg-background/60 px-3 py-2 text-sm text-foreground outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";
const labelCls = "mb-1 block text-xs font-medium text-muted-foreground";

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
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border bg-popover p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <h3 className="text-base font-semibold text-foreground">记录一场面试</h3>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-secondary/40 hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">关联投递记录（可选）</Label>
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
            <Label className="mb-1 block text-[11px] text-muted-foreground">公司{!link && " *"}（选关联后自动带出）</Label>
            <Input value={company} onChange={(e) => setCompany(e.target.value)}  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">岗位</Label>
            <Input value={role} onChange={(e) => setRole(e.target.value)}  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">轮次</Label>
            <select value={round} onChange={(e) => setRound(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_ROUNDS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">面试时间</Label>
            <Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)}  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">形式</Label>
            <select value={form} onChange={(e) => setForm(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_FORMS.map((f) => (
                <option key={f}>{f}</option>
              ))}
            </select>
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">结果</Label>
            <select value={result} onChange={(e) => setResult(e.target.value)} className={`${inputCls} cursor-pointer`}>
              {INTERVIEW_RESULTS.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">面试官</Label>
            <Input value={interviewer} onChange={(e) => setInterviewer(e.target.value)}  />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">问题记录</Label>
            <textarea
              value={questions}
              onChange={(e) => setQuestions(e.target.value)}
              rows={3}
              placeholder="被问了什么？按问题逐条记"
              className={`${inputCls} resize-y`}
            />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">我的回答要点</Label>
            <textarea
              value={answers}
              onChange={(e) => setAnswers(e.target.value)}
              rows={3}
              placeholder="当时怎么答的？只记要点"
              className={`${inputCls} resize-y`}
            />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">复盘与改进</Label>
            <textarea
              value={retro}
              onChange={(e) => setRetro(e.target.value)}
              rows={2}
              placeholder="下次怎么答得更好？复盘是面试记录里唯一能复利的部分"
              className={`${inputCls} resize-y`}
            />
          </div>
        </div>

        {error && <p className="mt-4 text-xs text-destructive">{error}</p>}

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg border border-border px-4 py-2 text-sm text-foreground transition-colors hover:bg-secondary/40"
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={saving}
            className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-5 py-2 text-sm font-medium text-foreground transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
