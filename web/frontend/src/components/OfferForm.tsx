import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { api, type Application, type Offer } from "../api";

const inputCls =
  "w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";
const labelCls = "mb-1 block text-xs font-medium text-slate-400";

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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
      <div className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-white">记录 Offer 事实</h3>
            <p className="mt-0.5 text-xs text-slate-500">
              只录你已知的事实。怎么选，由你看完所有事实后自己决定
            </p>
          </div>
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
              <option value="">不关联</option>
              {apps.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.id} · {a.公司} {a.岗位}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className={labelCls}>公司{!link && " *"}</label>
            <input value={company} onChange={(e) => setCompany(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>岗位</label>
            <input value={role} onChange={(e) => setRole(e.target.value)} className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>薪资构成</label>
            <input value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="如：月薪 x14 + 年终 x2" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>月薪</label>
            <input value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="如：11k" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>年终</label>
            <input value={bonus} onChange={(e) => setBonus(e.target.value)} placeholder="如：2 个月" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>签字费</label>
            <input value={signon} onChange={(e) => setSignon(e.target.value)} placeholder="如：1w（一次性）" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>股票期权</label>
            <input value={equity} onChange={(e) => setEquity(e.target.value)} placeholder="如：无 / 若干 RSU" className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>工作地点</label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} className={inputCls} />
          </div>
          <div>
            <label className={labelCls}>答复截止日</label>
            <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>其他条件</label>
            <input value={conditions} onChange={(e) => setConditions(e.target.value)} placeholder="如：税前；试用期 80%；竞业条款待确认" className={inputCls} />
          </div>
          <div className="col-span-2">
            <label className={labelCls}>备注</label>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="如：口头 offer，等书面" className={inputCls} />
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
            className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-5 py-2 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
