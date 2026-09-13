import { useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { api, type Application, type Offer } from "../api";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { FormField } from "./FormField";
import { ApplicationSelect } from "./ApplicationSelect";

/** 表单草稿：12 个字段收成一个对象，避免 12 组 useState + setter 散在组件里 */
type Draft = {
  link: string;
  company: string;
  role: string;
  salary: string;
  monthly: string;
  bonus: string;
  signon: string;
  equity: string;
  location: string;
  deadline: string;
  conditions: string;
  note: string;
};

const EMPTY: Draft = {
  link: "",
  company: "",
  role: "",
  salary: "",
  monthly: "",
  bonus: "",
  signon: "",
  equity: "",
  location: "",
  deadline: "",
  conditions: "",
  note: "",
};

function OfferFields({
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
        <ApplicationSelect value={d.link} onPick={onPick} />
      </FormField>

      <FormField label={t("form.company") + (d.link ? "" : t("form.requiredSuffix"))}>
        <Input value={d.company} onChange={(e) => set("company", e.target.value)} />
      </FormField>
      <FormField label={t("offer.field.role")}>
        <Input value={d.role} onChange={(e) => set("role", e.target.value)} />
      </FormField>
      <FormField label={t("offer.salary")} className="col-span-2">
        <Input
          value={d.salary}
          onChange={(e) => set("salary", e.target.value)}
          placeholder={t("offer.salaryPlaceholder")}
        />
      </FormField>
      <FormField label={t("offer.field.monthly")}>
        <Input value={d.monthly} onChange={(e) => set("monthly", e.target.value)} placeholder={t("offer.monthlyPlaceholder")} />
      </FormField>
      <FormField label={t("offer.field.bonus")}>
        <Input value={d.bonus} onChange={(e) => set("bonus", e.target.value)} placeholder={t("offer.bonusPlaceholder")} />
      </FormField>
      <FormField label={t("offer.field.signOn")}>
        <Input value={d.signon} onChange={(e) => set("signon", e.target.value)} placeholder={t("offer.signOnPlaceholder")} />
      </FormField>
      <FormField label={t("offer.field.equity")}>
        <Input value={d.equity} onChange={(e) => set("equity", e.target.value)} placeholder={t("offer.equityPlaceholder")} />
      </FormField>
      <FormField label={t("offer.field.location")}>
        <Input value={d.location} onChange={(e) => set("location", e.target.value)} />
      </FormField>
      <FormField label={t("offer.field.deadline")}>
        <Input type="date" value={d.deadline} onChange={(e) => set("deadline", e.target.value)} />
      </FormField>
      <FormField label={t("offer.field.other")} className="col-span-2">
        <Input
          value={d.conditions}
          onChange={(e) => set("conditions", e.target.value)}
          placeholder={t("offer.conditionsPlaceholder")}
        />
      </FormField>
      <FormField label={t("form.note")} className="col-span-2">
        <Input
          value={d.note}
          onChange={(e) => set("note", e.target.value)}
          placeholder={t("offer.notePlaceholder")}
        />
      </FormField>
    </div>
  );
}

export default function OfferForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (row: Offer) => void;
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
      .createOffer({
        关联记录: d.link,
        公司: d.company,
        岗位: d.role,
        薪资构成: d.salary,
        月薪: d.monthly,
        年终: d.bonus,
        签字费: d.signon,
        股票期权: d.equity,
        工作地点: d.location,
        答复截止日: d.deadline,
        其他条件: d.conditions,
        备注: d.note,
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
        <DialogHeader className="mb-5 flex-row items-start justify-between space-y-0">
          <div>
            <DialogTitle>{t("offer.formTitle")}</DialogTitle>
            <DialogDescription className="mt-0.5">
              {t("offer.formDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <OfferFields d={d} set={set} onPick={pickApp} />

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
