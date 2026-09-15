import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Megaphone, Plus, X } from "lucide-react";
import {
  api,
  TALK_ATTEND,
  TALK_FORMS,
  type Application,
  type Talk,
} from "../api";
import { domainLabel } from "../lib/domainLabels";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input, Textarea } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
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

function TalkForm({
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

export default function TalkList() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Talk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const reload = () => {
    api
      .listTalks()
      .then((r) => {
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(reload, []);

  // 行内改「是否参加」：改完即存（与面试列表的行内结果下拉同款）
  const setAttend = (id: string, v: string) => {
    api
      .updateTalk(id, { 是否参加: v })
      .then(() => reload())
      .catch((e: Error) => setError(e.message));
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          {t("talk.summary", { count: rows.length })}
        </p>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={api.talksIcsUrl()} title={t("talk.icsTitle")}>
              <Download size={14} /> {t("talk.exportIcs")}
            </a>
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t("talk.add")}
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：骨架 / 空态 / 列表（错误条显示时不与骨架同屏） */}
      {!loaded && !error
        ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)
        : null}
      {loaded && !error && rows.length === 0 ? (
        <Card className="flex flex-col items-center rounded-lg border-dashed p-8 text-center">
          <Megaphone size={28} className="mb-3 text-muted-foreground/70" />
          <p className="text-sm text-muted-foreground">{t("talk.emptyTitle")}</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground/70">
            {t("talk.emptyHint", { action: t("talk.add") })}
          </p>
        </Card>
      ) : null}

      {rows.map((r) => (
        <Card key={r.宣讲会id} className="rounded-lg p-3.5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {r.公司 || "—"}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {r.时间 || t("talk.whenTbd")}
                {r.形式 && ` · ${domainLabel("talkForm", r.形式, t)}`}
                {r.关联记录 && ` · ${t("interview.related", { value: r.关联记录 })}`}
              </p>
            </div>
            <Select value={r.是否参加} onValueChange={(v) => setAttend(r.宣讲会id, v)}>
              <SelectTrigger
                className="h-7 w-24 shrink-0 text-xs"
                aria-label={t("talk.attendAria", { company: r.公司 })}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TALK_ATTEND.map((o) => (
                  <SelectItem key={o} value={o} className="text-xs">
                    {domainLabel("talkAttend", o, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 地点或链接：URL 渲染成可点链接，纯地点按文本显示 */}
          {r.地点或链接 &&
            (/^https?:/i.test(r.地点或链接) ? (
              <a
                href={r.地点或链接}
                target="_blank"
                rel="noreferrer"
                title={t("talk.placeLinkOpen")}
                className="mt-1.5 inline-block text-xs text-primary hover:underline"
              >
                {t("talk.placeLinkOpen")}
              </a>
            ) : (
              <p className="mt-1.5 text-xs text-muted-foreground">{r.地点或链接}</p>
            ))}

          {r.收获 && (
            <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground/90">
              {r.收获}
            </p>
          )}
        </Card>
      ))}

      {showForm && (
        <TalkForm
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}
    </div>
  );
}
