import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Check,
  Copy,
  CornerDownRight,
  Mail as MailIcon,
  Pencil,
  Plus,
  X,
} from "lucide-react";
import {
  api,
  MAIL_DIRECTIONS,
  MAIL_TAGS,
  type Application,
  type Mail,
} from "../api";
import { previewDeleteRecord } from "../lib/records";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import DeleteRecordButton from "./DeleteRecordButton";
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

/**
 * 邮件记录（批 4.5）：往来邮件的独立台账——面试邀约、笔试通知、拒信都记进来，
 * 与投递记录用「关联记录」相连。
 *
 * 两条与后端同源的边界（不在此处另造口径）：
 * - **不自动改阶段**：这里只入账与查询；阶段流转一律走人工确认的链路；
 * - **深链诚实降级**：_openLink.kind = custom/gmail 才给「打开原邮件」；
 *   none（Outlook/QQ/163 等）显示「复制主题去邮箱搜索」，不造假链接。
 */

/** 表单草稿（`link` = 关联的投递记录 id）。 */
type Draft = {
  messageId: string;
  link: string;
  direction: string;
  subject: string;
  sender: string;
  when: string;
  url: string;
  tag: string;
};

const EMPTY: Draft = {
  messageId: "",
  link: "",
  direction: "收",
  subject: "",
  sender: "",
  when: "",
  url: "",
  tag: "其他",
};

/** Mail → Draft 映射（编辑模式预填）：日期在 CSV 里是空格分隔，input 要 T 分隔。 */
function draftFromMail(m: Mail): Draft {
  return {
    messageId: m.消息id ?? "",
    link: m.关联记录 ?? "",
    direction: m.方向 || "收",
    subject: m.主题 ?? "",
    sender: m.发件人 ?? "",
    when: (m.日期 ?? "").replace(" ", "T"),
    url: m.webmail链接 ?? "",
    tag: m.标签 || "其他",
  };
}

function MailForm({
  onClose,
  onSaved,
  initial,
}: {
  onClose: () => void;
  onSaved: () => void;
  /** 编辑模式（2026-09-17 收尾批）：给初始值即走 PATCH；缺省为新建 */
  initial?: Mail;
}) {
  const { t } = useTranslation();
  const [d, setD] = useState<Draft>(initial ? draftFromMail(initial) : EMPTY);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) =>
    setD((p) => ({ ...p, [k]: v }));

  // 选中关联记录时带出（与面试/宣讲会表单同款：只记 link，公司从主表带）
  const pickApp = (app: Application | null) =>
    setD((p) => ({ ...p, link: app?.id ?? "" }));

  const submit = () => {
    if (!d.subject.trim()) {
      setError(t("mail.subjectRequiredError"));
      return;
    }
    setSaving(true);
    setError(null);
    const body: Partial<Mail> = {
      关联记录: d.link,
      方向: d.direction,
      主题: d.subject,
      发件人: d.sender,
      // datetime-local 产生 "2026-09-16T10:00"，换成与 CSV 一致的空格分隔
      日期: d.when.replace("T", " "),
      webmail链接: d.url,
      标签: d.tag,
    };
    // 消息id 是去重键：仅新建时可写（后端 PATCH 亦不收该字段）
    if (!initial) body.消息id = d.messageId;
    const request = initial
      ? api.updateMail(initial.邮件id, body)
      : api.createMail(body);
    request
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
            <DialogTitle>
            {initial ? t("mail.editTitle") : t("mail.formTitle")}
          </DialogTitle>
            {/* Radix 要求 DialogContent 有可读描述，否则开发态会告警 */}
            <DialogDescription className="mt-0.5">
              {t("mail.formDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-4">
          <FormField label={t("mail.linkApp")} className="col-span-2">
            <ApplicationSelect value={d.link} onPick={pickApp} emptyLabel={t("form.linkAppNone")} />
          </FormField>
          <FormField label={t("mail.subject") + t("form.requiredSuffix")} className="col-span-2">
            <Input
              value={d.subject}
              onChange={(e) => set("subject", e.target.value)}
              placeholder={t("mail.subjectPlaceholder")}
            />
          </FormField>
          <FormField label={t("mail.tag")}>
            <Select value={d.tag} onValueChange={(v) => set("tag", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MAIL_TAGS.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={t("mail.direction")}>
            <Select value={d.direction} onValueChange={(v) => set("direction", v)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MAIL_DIRECTIONS.map((o) => (
                  <SelectItem key={o} value={o}>
                    {o}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FormField>
          <FormField label={t("mail.date")}>
            <Input
              type="datetime-local"
              value={d.when}
              onChange={(e) => set("when", e.target.value)}
            />
          </FormField>
          <FormField label={t("mail.sender")}>
            <Input
              value={d.sender}
              onChange={(e) => set("sender", e.target.value)}
              placeholder={t("mail.senderPlaceholder")}
            />
          </FormField>
          <FormField label={t("mail.messageId")} className="col-span-2">
            <Input
              value={d.messageId}
              onChange={(e) => set("messageId", e.target.value)}
              placeholder={t("mail.messageIdPlaceholder")}
              // 消息id 是去重键：建立后不可改（后端 PATCH 亦不收该字段）
              disabled={!!initial}
            />
          </FormField>
          <FormField label={t("mail.webmailUrl")} className="col-span-2">
            <Input
              value={d.url}
              onChange={(e) => set("url", e.target.value)}
              placeholder={t("mail.webmailUrlPlaceholder")}
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

export default function MailList() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Mail[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showForm, setShowForm] = useState(false);
  // 编辑 / 详情（2026-09-17 收尾批）：null = 关闭，否则为被编辑的行——详情就是编辑弹窗
  const [editing, setEditing] = useState<Mail | null>(null);
  // 复制主题的短暂反馈（无深链邮箱的降级路径）
  const [copied, setCopied] = useState<string | null>(null);

  const reload = () => {
    api
      .listMails()
      .then((r) => {
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(reload, []);

  // 行内改标签：改完即存（与宣讲会的「是否参加」同款）
  const setTag = (id: string, v: string) => {
    api
      .updateMail(id, { 标签: v })
      .then(() => reload())
      .catch((e: Error) => setError(e.message));
  };

  // 跳到追踪表并展开该记录（2026-09-17 收尾批）：复用看板的 focusId 下钻——
  // sessionStorage 传参 + hash 切页；App 是条件渲染，切过去会重挂载并消费。
  const jumpToRecord = (id: string) => {
    try {
      sessionStorage.setItem("jobws_drill", JSON.stringify({ focusId: id }));
    } catch {
      // 存储不可用：退化为不带聚焦的跳转
    }
    window.location.hash = "applications";
  };

  // 删除已改为两段式（DeleteRecordButton：预览 → 确认弹窗 → 凭令牌落盘），
  // 上一版「点两次直删」的本地状态与 remove() 已撤除（批 D）。

  const copySubject = (r: Mail) => {
    if (!navigator.clipboard?.writeText) return;
    navigator.clipboard
      .writeText(r.主题)
      .then(() => {
        setCopied(r.邮件id);
        setTimeout(() => setCopied(null), 1500);
      })
      .catch(() => {
        /* 剪贴板不可用时静默：用户仍可手动选中主题 */
      });
  };

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          {t("mail.summary", { count: rows.length })}
        </p>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t("mail.add")}
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：骨架 / 空态 / 列表（错误条显示时不与骨架同屏） */}
      {!loaded && !error
        ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)
        : null}
      {loaded && !error && rows.length === 0 ? (
        <Card className="flex flex-1 flex-col justify-center rounded-lg border-dashed">
          <EmptyState
            icon={<MailIcon size={20} />}
            title={t("mail.emptyTitle")}
            description={t("mail.emptyHint", { action: t("mail.add") })}
            action={
              <Button onClick={() => setShowForm(true)}>
                <Plus size={14} /> {t("mail.add")}
              </Button>
            }
          />
        </Card>
      ) : null}

      {rows.map((r) => (
        <Card key={r.邮件id} className="rounded-lg p-3.5">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-foreground" title={r.主题}>
                {r.主题 || "—"}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {r.日期 || t("mail.dateTbd")}
                {r.发件人 && ` · ${r.发件人}`}
                {` · ${r.方向}`}
              </p>
              {/* 关联记录可跳转（2026-09-17 收尾批）：台账 ↔ 追踪表互相可见——
                  点击回到那条投递并自动展开（复用看板 focusId 下钻） */}
              {r.关联记录 && (
                <button
                  type="button"
                  onClick={() => jumpToRecord(r.关联记录)}
                  title={t("mail.jumpToRecord")}
                  className="mt-0.5 inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline"
                >
                  <CornerDownRight size={12} />
                  {t("interview.related", { value: r.关联记录 })}
                </button>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Select value={r.标签} onValueChange={(v) => setTag(r.邮件id, v)}>
                <SelectTrigger
                  className="h-7 w-24 shrink-0 text-xs"
                  aria-label={t("mail.tagAria", { subject: r.主题 })}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MAIL_TAGS.map((o) => (
                    <SelectItem key={o} value={o} className="text-xs">
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* 编辑（详情）与删除（批 D 改造：预览 → 确认弹窗 → 凭令牌落盘；
                  旧版「点两次直删」已撤——删除与全站其余写操作同走两段式） */}
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                title={t("mail.editTitle")}
                aria-label={t("common.edit")}
                onClick={() => setEditing(r)}
              >
                <Pencil size={13} />
              </Button>
              <DeleteRecordButton
                preview={() => previewDeleteRecord("mails", r.邮件id)}
                onDeleted={reload}
              />
            </div>
          </div>

          {/* 打开原邮件：custom/gmail 给真链接；none 诚实降级为「复制主题搜索」 */}
          <div className="mt-1.5 flex items-center gap-3">
            {r._openLink?.url ? (
              <a
                href={r._openLink.url}
                target="_blank"
                rel="noreferrer"
                title={r._openLink.kind === "gmail" ? t("mail.gmailHint") : t("mail.openTitle")}
                className="inline-block text-xs text-primary hover:underline"
              >
                {t("mail.open")}
              </a>
            ) : (
              <>
                <span className="text-xs text-muted-foreground">{t("mail.noLinkHint")}</span>
                <button
                  type="button"
                  onClick={() => copySubject(r)}
                  title={t("mail.copySubjectTitle")}
                  className="inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline"
                >
                  {copied === r.邮件id ? <Check size={12} /> : <Copy size={12} />}
                  {copied === r.邮件id ? t("mail.copied") : t("mail.copySubject")}
                </button>
              </>
            )}
          </div>
        </Card>
      ))}

      {showForm && (
        <MailForm
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}

      {/* 编辑（详情）弹窗：同表单复用，initial 驱动 PATCH 分支 */}
      {editing && (
        <MailForm
          initial={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
