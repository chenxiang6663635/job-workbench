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
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { FormField } from "./FormField";
import { ApplicationSelect } from "./ApplicationSelect";

/** 表单草稿：11 个字段收成一个对象，避免 11 组 useState + setter 散在组件里 */
type Draft = {
  link: string;
  company: string;
  role: string;
  round: string;
  when: string;
  form: string;
  interviewer: string;
  questions: string;
  answers: string;
  retro: string;
  result: string;
};

const EMPTY: Draft = {
  link: "",
  company: "",
  role: "",
  round: "一面",
  when: "",
  form: "视频",
  interviewer: "",
  questions: "",
  answers: "",
  retro: "",
  result: "待定",
};

/** 常量枚举下拉（选项即值，取值非空故无需哨兵） */
function EnumSelect({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {options.map((o) => (
          <SelectItem key={o} value={o}>
            {o}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function InterviewFields({
  d,
  set,
  onPick,
}: {
  d: Draft;
  set: <K extends keyof Draft>(k: K, v: Draft[K]) => void;
  onPick: (app: Application | null) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <FormField label="关联投递记录（可选）" className="col-span-2">
        <ApplicationSelect value={d.link} onPick={onPick} emptyLabel="不关联（如内推面试）" />
      </FormField>

      <FormField label={`公司${d.link ? "" : " *"}（选关联后自动带出）`}>
        <Input value={d.company} onChange={(e) => set("company", e.target.value)} />
      </FormField>
      <FormField label="岗位">
        <Input value={d.role} onChange={(e) => set("role", e.target.value)} />
      </FormField>
      <FormField label="轮次">
        <EnumSelect value={d.round} options={INTERVIEW_ROUNDS} onChange={(v) => set("round", v)} />
      </FormField>
      <FormField label="面试时间">
        <Input type="datetime-local" value={d.when} onChange={(e) => set("when", e.target.value)} />
      </FormField>
      <FormField label="形式">
        <EnumSelect value={d.form} options={INTERVIEW_FORMS} onChange={(v) => set("form", v)} />
      </FormField>
      <FormField label="结果">
        <EnumSelect value={d.result} options={INTERVIEW_RESULTS} onChange={(v) => set("result", v)} />
      </FormField>
      <FormField label="面试官" className="col-span-2">
        <Input value={d.interviewer} onChange={(e) => set("interviewer", e.target.value)} />
      </FormField>

      <FormField label="问题记录" className="col-span-2">
        <Textarea
          rows={3}
          value={d.questions}
          onChange={(e) => set("questions", e.target.value)}
          placeholder="被问了什么？按问题逐条记"
          className="resize-y"
        />
      </FormField>
      <FormField label="我的回答要点" className="col-span-2">
        <Textarea
          rows={3}
          value={d.answers}
          onChange={(e) => set("answers", e.target.value)}
          placeholder="当时怎么答的？只记要点"
          className="resize-y"
        />
      </FormField>
      <FormField label="复盘与改进" className="col-span-2">
        <Textarea
          rows={2}
          value={d.retro}
          onChange={(e) => set("retro", e.target.value)}
          placeholder="下次怎么答得更好？复盘是面试记录里唯一能复利的部分"
          className="resize-y"
        />
      </FormField>
    </div>
  );
}

export default function InterviewForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (row: Interview) => void;
}) {
  const [d, setD] = useState<Draft>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setD((p) => ({ ...p, [k]: v }));

  // 选中关联记录时带出公司与岗位；取消关联则保留已填写的内容
  const pickApp = (app: Application | null) =>
    setD((p) => ({
      ...p,
      link: app?.id ?? "",
      company: app?.公司 ?? p.company,
      role: app?.岗位 ?? p.role,
    }));

  const submit = () => {
    if (!d.link && !d.company.trim()) {
      setError("未关联投递记录时，公司必填");
      return;
    }
    setSaving(true);
    setError(null);
    api
      .createInterview({
        关联记录: d.link,
        公司: d.company,
        岗位: d.role,
        轮次: d.round,
        // datetime-local 产生 "2026-09-05T14:00"，换成与 CSV 一致的空格分隔
        面试时间: d.when.replace("T", " "),
        形式: d.form,
        面试官: d.interviewer,
        问题记录: d.questions,
        我的回答要点: d.answers,
        复盘与改进: d.retro,
        结果: d.result,
      })
      .then((row) => onSaved(row))
      .catch((e: Error) => {
        setError(e.message);
        setSaving(false);
      });
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl p-6">
        <DialogHeader className="mb-5 flex-row items-center justify-between space-y-0">
          <DialogTitle>记录一场面试</DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <InterviewFields d={d} set={set} onPick={pickApp} />

        {error && <p className="mt-4 text-xs text-destructive">{error}</p>}

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
