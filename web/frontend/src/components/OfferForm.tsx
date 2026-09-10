import { useState } from "react";
import { X } from "lucide-react";
import { api, type Application, type Offer } from "../api";
import {
  Dialog,
  DialogClose,
  DialogContent,
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
  return (
    <div className="grid grid-cols-2 gap-4">
      <FormField label="关联投递记录（可选）" className="col-span-2">
        <ApplicationSelect value={d.link} onPick={onPick} />
      </FormField>

      <FormField label={`公司${d.link ? "" : " *"}`}>
        <Input value={d.company} onChange={(e) => set("company", e.target.value)} />
      </FormField>
      <FormField label="岗位">
        <Input value={d.role} onChange={(e) => set("role", e.target.value)} />
      </FormField>
      <FormField label="薪资构成" className="col-span-2">
        <Input
          value={d.salary}
          onChange={(e) => set("salary", e.target.value)}
          placeholder="如：月薪 x14 + 年终 x2"
        />
      </FormField>
      <FormField label="月薪">
        <Input value={d.monthly} onChange={(e) => set("monthly", e.target.value)} placeholder="如：11k" />
      </FormField>
      <FormField label="年终">
        <Input value={d.bonus} onChange={(e) => set("bonus", e.target.value)} placeholder="如：2 个月" />
      </FormField>
      <FormField label="签字费">
        <Input value={d.signon} onChange={(e) => set("signon", e.target.value)} placeholder="如：1w（一次性）" />
      </FormField>
      <FormField label="股票期权">
        <Input value={d.equity} onChange={(e) => set("equity", e.target.value)} placeholder="如：无 / 若干 RSU" />
      </FormField>
      <FormField label="工作地点">
        <Input value={d.location} onChange={(e) => set("location", e.target.value)} />
      </FormField>
      <FormField label="答复截止日">
        <Input type="date" value={d.deadline} onChange={(e) => set("deadline", e.target.value)} />
      </FormField>
      <FormField label="其他条件" className="col-span-2">
        <Input
          value={d.conditions}
          onChange={(e) => set("conditions", e.target.value)}
          placeholder="如：税前；试用期 80%；竞业条款待确认"
        />
      </FormField>
      <FormField label="备注" className="col-span-2">
        <Input
          value={d.note}
          onChange={(e) => set("note", e.target.value)}
          placeholder="如：口头 offer，等书面"
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
            <DialogTitle>记录 Offer 事实</DialogTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              只录你已知的事实。怎么选，由你看完所有事实后自己决定
            </p>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <OfferFields d={d} set={set} onPick={pickApp} />

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
