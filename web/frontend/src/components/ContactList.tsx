import { useEffect, useState } from "react";
import { ChevronDown, PhoneCall, Plus, UserRound } from "lucide-react";
import { api, type Contact } from "../api";

const inputCls =
  "w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";

// 下次跟进早于今天 → 超期，琥珀提醒；今天 → 今日跟进，绿色
function followState(date: string): "overdue" | "today" | null {
  if (!date) return null;
  const today = new Date().toISOString().slice(0, 10);
  if (date < today) return "overdue";
  if (date === today) return "today";
  return null;
}

export default function ContactList() {
  const [rows, setRows] = useState<Contact[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [contact, setContact] = useState("");
  const [source, setSource] = useState("");
  const [nextFollow, setNextFollow] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const reload = () => {
    api
      .listContacts()
      .then((r) => {
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(reload, []);

  const submit = () => {
    if (!name.trim()) {
      setError("姓名必填");
      return;
    }
    setSaving(true);
    setError(null);
    api
      .createContact({
        姓名: name,
        角色: role,
        公司: company,
        联系方式: contact,
        来源: source,
        下次跟进: nextFollow,
        备注: note,
      })
      .then(() => {
        setShowForm(false);
        setName("");
        setRole("");
        setCompany("");
        setContact("");
        setSource("");
        setNextFollow("");
        setNote("");
        setSaving(false);
        reload();
      })
      .catch((e: Error) => {
        setError(e.message);
        setSaving(false);
      });
  };

  // 标记已联系：最近联系=今天，下次跟进清空
  const markContacted = (c: Contact) => {
    const today = new Date().toISOString().slice(0, 10);
    api
      .updateContact(c.联系人id, { 最近联系: today, 下次跟进: "" })
      .then(reload)
      .catch((e: Error) => setError(e.message));
  };

  const form = (
    <div className="space-y-3 rounded-2xl border border-accent/30 bg-ink-900/70 p-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <input className={inputCls} placeholder="姓名 *" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={inputCls} placeholder="角色（HR / 技术面 / 猎头）" value={role} onChange={(e) => setRole(e.target.value)} />
        <input className={inputCls} placeholder="公司" value={company} onChange={(e) => setCompany(e.target.value)} />
        <input className={inputCls} placeholder="联系方式（微信 / 手机 / 邮箱）" value={contact} onChange={(e) => setContact(e.target.value)} />
        <input className={inputCls} placeholder="来源（BOSS / 内推 / 官网）" value={source} onChange={(e) => setSource(e.target.value)} />
        <input type="date" className={inputCls} title="下次跟进" value={nextFollow} onChange={(e) => setNextFollow(e.target.value)} />
      </div>
      <input className={inputCls} placeholder="备注（聊了什么、注意事项）" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex justify-end gap-2">
        <button onClick={() => setShowForm(false)} className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5">
          取消
        </button>
        <button onClick={submit} disabled={saving} className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-5 py-2 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50">
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {loaded && `${rows.length} 位联系人 · 有下次跟进日期的排最前，超期的会标琥珀色`}
        </p>
        <button
          onClick={() => setShowForm((v) => !v)}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-gradient-to-r from-accent to-accent-dim px-3.5 py-2 text-xs font-medium text-white transition-all hover:opacity-90"
        >
          {showForm ? <ChevronDown size={14} /> : <Plus size={14} />}
          {showForm ? "收起" : "记联系人"}
        </button>
      </div>

      {showForm && form}
      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-xs text-bad">{error}</div>
      )}

      {loaded && rows.length === 0 && (
        <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-8 text-center">
          <UserRound size={28} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm text-slate-400">还没有联系人记录</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            HR 的名字、聊到哪一步、答应什么时候回——
            <br />
            流程感很强的招聘，靠这些细节维系
          </p>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((c) => {
          const st = followState(c.下次跟进);
          return (
            <div
              key={c.联系人id}
              className={`rounded-xl border p-4 transition-all duration-200 hover:-translate-y-0.5 ${
                st === "overdue"
                  ? "border-warn/40 bg-warn/5"
                  : "border-white/10 bg-ink-900/60 hover:border-white/20"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium text-slate-100">{c.姓名}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {[c.角色, c.公司].filter(Boolean).join(" · ") || "（未填角色）"}
                  </p>
                </div>
                <span className="rounded-md border border-white/10 bg-ink-950/60 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {c.联系人id}
                </span>
              </div>

              {c.联系方式 && (
                <p className="mt-2 text-xs text-slate-400">
                  {c.联系方式}
                  {c.来源 && <span className="ml-1.5 text-slate-600">（{c.来源}）</span>}
                </p>
              )}

              <div className="mt-2.5 flex items-center justify-between text-xs">
                <span
                  className={
                    st === "overdue"
                      ? "font-medium text-warn"
                      : st === "today"
                      ? "font-medium text-good"
                      : "text-slate-500"
                  }
                >
                  {st === "overdue"
                    ? `跟进超期：${c.下次跟进}`
                    : st === "today"
                    ? "今天该跟进"
                    : c.下次跟进
                    ? `下次跟进：${c.下次跟进}`
                    : "暂无跟进计划"}
                </span>
                <button
                  onClick={() => markContacted(c)}
                  title="把最近联系记为今天，并清掉跟进计划"
                  className="flex cursor-pointer items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-slate-400 transition-colors hover:border-accent/40 hover:text-accent"
                >
                  <PhoneCall size={11} /> 已联系
                </button>
              </div>

              {c.备注 && (
                <p className="mt-2 border-t border-white/5 pt-2 text-xs leading-relaxed text-slate-500">
                  {c.备注}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
