import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, type Application, type Offer } from "../api";
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

export default function OfferForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: (row: Offer) => void;
}) {
  const [apps, setApps] = useState<Application[]>([]);
  const [link, setLink] = useState("");
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [salary, setSalary] = useState("");
  const [monthly, setMonthly] = useState("");
  const [bonus, setBonus] = useState("");
  const [signon, setSignon] = useState("");
  const [equity, setEquity] = useState("");
  const [location, setLocation] = useState("");
  const [deadline, setDeadline] = useState("");
  const [conditions, setConditions] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      .createOffer({
        关联记录: link,
        公司: company,
        岗位: role,
        薪资构成: salary,
        月薪: monthly,
        年终: bonus,
        签字费: signon,
        股票期权: equity,
        工作地点: location,
        答复截止日: deadline,
        其他条件: conditions,
        备注: note,
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
          <div>
            <h3 className="text-base font-semibold text-foreground">记录 Offer 事实</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              只录你已知的事实。怎么选，由你看完所有事实后自己决定
            </p>
          </div>
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
              <option value="">不关联</option>
              {apps.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} · {a.公司} {a.岗位}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">公司{!link && " *"}</Label>
            <Input value={company} onChange={(e) => setCompany(e.target.value)}  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">岗位</Label>
            <Input value={role} onChange={(e) => setRole(e.target.value)}  />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">薪资构成</Label>
            <Input value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="如：月薪 x14 + 年终 x2"  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">月薪</Label>
            <Input value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="如：11k"  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">年终</Label>
            <Input value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="如：2 个月"  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">签字费</Label>
            <Input value={signon} onChange={(e) => setSignon(e.target.value)} placeholder="如：1w（一次性）"  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">股票期权</Label>
            <Input value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="如：无 / 若干 RSU"  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">工作地点</Label>
            <Input value={location} onChange={(e) => setLocation(e.target.value)}  />
          </div>
          <div>
            <Label className="mb-1 block text-[11px] text-muted-foreground">答复截止日</Label>
            <Input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)}  />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">其他条件</Label>
            <Input value={conditions} onChange={(e) => setConditions(e.target.value)} placeholder="如：税前；试用期 80%；竞业条款待确认"  />
          </div>
          <div className="col-span-2">
            <Label className="mb-1 block text-[11px] text-muted-foreground">备注</Label>
            <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="如：口头 offer，等书面"  />
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
            className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-5 py-2 text-sm font-medium text-foreground transition-all hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
