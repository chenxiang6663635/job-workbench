import { useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
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
  DialogDescription,
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
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-2 gap-4">
      <FormField label={t("form.linkApp")} className="col-span-2">
        <ApplicationSelect value={d.link} onPick={onPick} emptyLabel={t("form.linkAppNone")} />
      </FormField>

      {/* 公司的必填标记与「自动带出」提示拼在 label 后面，不进 key */}
      <FormField
        label={
          t("form.company") +
          (d.link ? "" : t("form.requiredSuffix")) +
          t("form.autofillHint")
        }
      >
        <Input value={d.company} onChange={(e) => set("company", e.target.value)} />
      </FormField>
      <FormField label={t("form.role")}>
        <Input value={d.role} onChange={(e) => set("role", e.target.value)} />
      </FormField>
      <FormField label={t("interview.round")}>
        <EnumSelect value={d.round} options={INTERVIEW_ROUNDS} onChange={(v) => set("round", v)} />
      </FormField>
      <FormField label={t("interview.when")}>
        <Input type="datetime-local" value={d.when} onChange={(e) => set("when", e.target.value)} />
      </FormField>
      <FormField label={t("interview.form")}>
        <EnumSelect value={d.form} options={INTERVIEW_FORMS} onChange={(v) => set("form", v)} />
      </FormField>
      <FormField label={t("interview.result")}>
        <EnumSelect value={d.result} options={INTERVIEW_RESULTS} onChange={(v) => set("result", v)} />
      </FormField>
      <FormField label={t("interview.interviewerLabel")} className="col-span-2">
        <Input value={d.interviewer} onChange={(e) => set("interviewer", e.target.value)} />
      </FormField>

      {/* 三段 label 与详情页表头是同一组文案（interview.section*） */}
      <FormField label={t("interview.sectionQuestions")} className="col-span-2">
        <Textarea
          rows={3}
          value={d.questions}
          onChange={(e) => set("questions", e.target.value)}
          placeholder={t("interview.questionsPlaceholder")}
          className="resize-y"
        />
      </FormField>
      <FormField label={t("interview.sectionAnswers")} className="col-span-2">
        <Textarea
          rows={3}
          value={d.answers}
          onChange={(e) => set("answers", e.target.value)}
          placeholder={t("interview.answersPlaceholder")}
          className="resize-y"
        />
      </FormField>
      <FormField label={t("interview.sectionRetro")} className="col-span-2">
        <Textarea
          rows={2}
          value={d.retro}
          onChange={(e) => set("retro", e.target.value)}
          placeholder={t("interview.retroPlaceholder")}
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
  const { t } = useTranslation();
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
      setError(t("form.companyRequiredError"));
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
          <div>
            <DialogTitle>{t("interview.formTitle")}</DialogTitle>
            {/* Radix 要求 DialogContent 有可读描述，否则开发态会告警 */}
            <DialogDescription className="mt-0.5">
              {t("interview.formDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <InterviewFields d={d} set={set} onPick={pickApp} />

        {error && <p className="mt-4 text-xs text-destructive">{error}</p>}

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={saving}>
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
