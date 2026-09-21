// 宣讲会新增表单（2026-09-21 从 TalkList.tsx 拆出）：TalkList 逼近规模水位，
// 而表单是自成一体的 Dialog 段（草稿 / 校验 / 提交），整体搬走比在原文件里挤清楚。
// 与 InterviewForm / OfferForm 同属「表单组件」一族。
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { api, TALK_ATTEND, TALK_FORMS, type Application } from "../api";
import { domainLabel } from "../lib/domainLabels";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { ApplicationSelect } from "./ApplicationSelect";
import { FormField } from "./FormField";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";

/** 表单草稿（`link` = 关联的投递记录 id；「地点或链接」是活动地址，与它无关）。 */
type Draft = {
  company: string;
  when: string;
  form: string;
  place: string;
  link: string;
  attend: string;
  gain: string;
  note: string;
};

const EMPTY: Draft = {
  company: "",
  when: "",
  form: "线下",
  place: "",
  link: "",
  attend: "待定",
  gain: "",
  note: "",
};

export default function TalkForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<Draft>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setD((p) => ({ ...p, [k]: v }));

  // 选中关联记录时带出公司；取消关联则保留已填写的内容（与面试表单同款）
  const pickApp = (app: Application | null) =>
    setD((p) => ({
      ...p,
      link: app?.id ?? "",
      company: app?.公司 ?? p.company,
    }));

  const submit = () => {
    if (!d.link && !d.company.trim()) {
      setError(t("talk.companyRequiredError"));
      return;
    }
    setSaving(true);
    setError(null);
    api
      .createTalk({
        公司: d.company,
        // datetime-local 产生 "2026-09-20T14:00"，换成与 CSV 一致的空格分隔
        时间: d.when.replace("T", " "),
        形式: d.form,
        地点或链接: d.place,
        关联记录: d.link,
        是否参加: d.attend,
        收获: d.gain,
        备注: d.note,
      })
      .then(() => onSaved())
      .catch((e: Error) => {
        setError(e.message);
        setSaving(false);
      });
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-lg p-6">
        <DialogHeader className="mb-5 flex-row items-center justify-between space-y-0">
          <div>
            <DialogTitle>{t("talk.formTitle")}</DialogTitle>
            {/* Radix 要求 DialogContent 有可读描述，否则开发态会告警 */}
            <DialogDescription className="mt-0.5">
              {t("talk.formDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <FormField label={t("talk.linkApp")} className="col-span-2">
            <ApplicationSelect value={d.link} onPick={pickApp} emptyLabel={t("form.linkAppNone")} />
          </FormField>
          <FormField
            label={
              t("talk.company") +
              (d.link ? "" : t("form.requiredSuffix")) +
              t("form.autofillHint")
            }
          >
            <Input value={d.company} onChange={(e) => set("company", e.target.value)} />
          </FormField>
          <FormField label={t("talk.when")}>
            <Input
              type="datetime-local"
              value={d.when}
              onChange={(e) => set("when", e.target.value)}
            />
          </FormField>
          <FormField label={t("talk.form")}>
            <Select value={d.form} onValueChange={(v) => set("form", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TALK_FORMS.map((o) => (
                  <SelectItem key={o} value={o}>
                    {domainLabel("talkForm", o, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={t("talk.attend")}>
            <Select value={d.attend} onValueChange={(v) => set("attend", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TALK_ATTEND.map((o) => (
                  <SelectItem key={o} value={o}>
                    {domainLabel("talkAttend", o, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={t("talk.place")} className="col-span-2">
            <Input
              value={d.place}
              onChange={(e) => set("place", e.target.value)}
              placeholder={t("talk.placePlaceholder")}
            />
          </FormField>
          <FormField label={t("talk.gain")} className="col-span-2">
            <Textarea
              rows={3}
              value={d.gain}
              onChange={(e) => set("gain", e.target.value)}
              placeholder={t("talk.gainPlaceholder")}
              className="resize-y"
            />
          </FormField>
          <FormField label={t("talk.note")} className="col-span-2">
            <Textarea
              rows={2}
              value={d.note}
              onChange={(e) => set("note", e.target.value)}
              className="resize-y"
            />
          </FormField>
        </div>

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
