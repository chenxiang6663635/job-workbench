import { useEffect, useState } from "react";
import { ChevronDown, PhoneCall, Plus, UserRound } from "lucide-react";
import { api, type Contact } from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";

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
    <Card className="space-y-3 rounded-2xl border-primary/30 p-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <Input placeholder="姓名 *" value={name} onChange={(e) => setName(e.target.value)} />
        <Input placeholder="角色（HR / 技术面 / 猎头）" value={role} onChange={(e) => setRole(e.target.value)} />
        <Input placeholder="公司" value={company} onChange={(e) => setCompany(e.target.value)} />
        <Input placeholder="联系方式（微信 / 手机 / 邮箱）" value={contact} onChange={(e) => setContact(e.target.value)} />
        <Input placeholder="来源（BOSS / 内推 / 官网）" value={source} onChange={(e) => setSource(e.target.value)} />
        <Input type="date" title="下次跟进" value={nextFollow} onChange={(e) => setNextFollow(e.target.value)} />
      </div>
      <Input placeholder="备注（聊了什么、注意事项）" value={note} onChange={(e) => setNote(e.target.value)} />
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={() => setShowForm(false)}>
          取消
        </Button>
        <Button onClick={submit} disabled={saving}>
          {saving ? "保存中…" : "保存"}
        </Button>
      </div>
    </Card>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {loaded && `${rows.length} 位联系人 · 有下次跟进日期的排最前，超期的会标琥珀色`}
        </p>
        <Button onClick={() => setShowForm((v) => !v)}>
          {showForm ? <ChevronDown size={14} /> : <Plus size={14} />}
          {showForm ? "收起" : "记联系人"}
        </Button>
      </div>

      {showForm && form}
      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条 */}
      {!loaded ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="flex flex-col items-center rounded-2xl border-dashed p-8 text-center">
          <UserRound size={28} className="mb-3 text-muted-foreground/70" />
          <p className="text-sm text-muted-foreground">还没有联系人记录</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground/70">
            HR 的名字、聊到哪一步、答应什么时候回——
            <br />
            流程感很强的招聘，靠这些细节维系
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((c) => {
            const st = followState(c.下次跟进);
            return (
              <Card
                key={c.联系人id}
                className={`rounded-xl p-4 transition-all duration-200 hover:-translate-y-0.5 ${
                  st === "overdue"
                    ? "border-warning/40 bg-warning/5"
                    : "hover:border-border-strong"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">{c.姓名}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {[c.角色, c.公司].filter(Boolean).join(" · ") || "（未填角色）"}
                    </p>
                  </div>
                  <Badge variant="outline" className="rounded-md px-1.5 py-0 text-[10px] font-mono">
                    {c.联系人id}
                  </Badge>
                </div>

                {c.联系方式 && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {c.联系方式}
                    {c.来源 && <span className="ml-1.5 text-muted-foreground/70">（{c.来源}）</span>}
                  </p>
                )}

                <div className="mt-2.5 flex items-center justify-between text-xs">
                  <span
                    className={
                      st === "overdue"
                        ? "font-medium text-warning"
                        : st === "today"
                        ? "font-medium text-success"
                        : "text-muted-foreground"
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
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => markContacted(c)}
                    title="把最近联系记为今天，并清掉跟进计划"
                    className="h-6 px-2 text-[11px]"
                  >
                    <PhoneCall size={11} /> 已联系
                  </Button>
                </div>

                {c.备注 && (
                  <p className="mt-2 border-t border-border pt-2 text-xs leading-relaxed text-muted-foreground">
                    {c.备注}
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
