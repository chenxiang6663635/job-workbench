import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { RANGE_OPTIONS, rangeLabelKey } from "../lib/imapRange";
import { Inbox, Loader2, RefreshCw, Search, X } from "lucide-react";
import ImapMessageRow from "./ImapMessageRow";
import { api, type ImapMessage } from "../api";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { ErrorBanner } from "./ErrorBanner";
import { EmptyState } from "./ui/empty";
import { Num } from "./ui/number";

interface Props {
  onClose: () => void;
  /** 选定邮件后把正文交给「粘贴邮件更新」对话框预填（用户仍可编辑再解析） */
  onUse: (body: string) => void;
  /** 「记入邮件台账」（批 4.5）：整条元数据交调用方落库（Message-ID/主题/发件人/日期） */
  onRecord?: (m: ImapMessage) => Promise<unknown>;
}

/**
 * 从邮箱只读拉取邮件（服务端按时间窗搜索，最新在前），选一封交给
 * 「解析 → 建议 → 确认」流程。
 *
 * 打开本对话框 = 一次显式点击，此时才连接邮箱（没有后台连接/定时轮询）。
 * 拉取是 dry-run：不动邮箱、也不动追踪表；写回只发生在用户于下一步
 * 逐条确认之后。凭证与服务器配置在「设置」页。
 */
export default function ImapFetchDialog({ onClose, onUse, onRecord }: Props) {
  const { t } = useTranslation();
  const [messages, setMessages] = useState<ImapMessage[] | null>(null);
  // 已记入台账的邮件（按 uid）：按钮原地变「已记录」——后端还有消息id 去重兜底
  const [recorded, setRecorded] = useState<Record<string, boolean>>({});
  // in-flight 的记录请求（防连点，审查 m-2）：pending 期间按钮禁用，成功才标记
  // recorded——无 Message-ID 的邮件没有后端去重兜底，连点会落两条一模一样的行
  const [recordingUid, setRecordingUid] = useState<string | null>(null);
  const [server, setServer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sinceDays, setSinceDays] = useState(30);
  const [query, setQuery] = useState("");
  // 展开「解析建议」的那一行（同一时刻只开一行，避免弹窗被卡片撑爆）
  const [suggestUid, setSuggestUid] = useState<string | null>(null);

  // 序号守卫：切窗口与手动刷新可以叠加发出，旧响应迟到会盖掉新窗口的列表
  const loadSeq = useRef(0);
  const load = () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError(null);
    setMessages(null); // 等待期间标题已是新范围，列表不许还是上一窗口的邮件
    api
      .fetchImapMessages({ limit: 50, since_days: sinceDays })
      .then(
        (r) => {
          if (seq !== loadSeq.current) return;
          setMessages(r.messages);
          setServer(r.server);
        },
        (e: Error) => {
          if (seq === loadSeq.current) setError(e.message);
        }
      )
      .then(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
  };

  // 切换时间窗即重新拉取（首次挂载也走这里）——用户改的是服务端搜索条件，
  // 不重拉的话列表与所选范围对不上
  useEffect(load, [sinceDays]);

  // 记入台账：一次只允许一条在飞——没有 Message-ID 的邮件没有后端去重兜底，
  // 连点会落两条一模一样的行（审查 m-2）。状态留在这一层，条目组件只发事件。
  const record = (m: ImapMessage) => {
    if (!onRecord || recordingUid) return;
    setRecordingUid(m.uid);
    onRecord(m)
      .then(() => setRecorded((prev) => ({ ...prev, [m.uid]: true })))
      .catch((e: Error) => setError(e.message))
      .finally(() => setRecordingUid((cur) => (cur === m.uid ? null : cur)));
  };

  const q = query.trim().toLowerCase();
  const filtered = (messages ?? []).filter(
    (m) => !q || (m.subject + " " + m.from + " " + m.body).toLowerCase().includes(q)
  );
  // 时间范围是个 labelKey（模块级常量存不下翻译后的字符串）
  const rangeKey = rangeLabelKey(sinceDays);
  const rangeLabel = rangeKey ? t(rangeKey) : "";

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[82vh] w-full max-w-2xl flex-col gap-0 rounded-lg p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Inbox size={16} className="text-primary" /> {t("imap.title")}
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          <DialogDescription className="text-sm">
            {t("imap.readonlyNote")}
            {server && <span className="text-muted-foreground">（{server}）</span>}
          </DialogDescription>

          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={String(sinceDays)}
              onValueChange={(v) => setSinceDays(Number(v))}
            >
              <SelectTrigger aria-label={t("imap.rangeLabel")} className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {t(o.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            {/* 本地筛选：不动服务端，只在已拉回的列表里找（对付广告邮件刷屏） */}
            <div className="relative min-w-[180px] flex-1">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                className="h-8 pl-8 text-xs"
                placeholder={t("imap.filterPlaceholder")}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>

            <Button
              variant="outline"
              className="h-8 px-3 text-xs"
              onClick={load}
              disabled={loading}
            >
              <RefreshCw size={14} /> {t("imap.refetch")}
            </Button>
          </div>

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {loading && (
            <p className="flex items-center gap-2 px-1 py-6 text-sm text-muted-foreground">
              <Loader2 size={15} className="animate-spin" /> {t("imap.fetching")}
            </p>
          )}

          {!loading && messages && messages.length === 0 && (
            <div className="rounded-lg border border-dashed border-border">
              <EmptyState
                icon={<Inbox size={20} />}
                title={t("imap.empty", { range: rangeLabel })}
                compact
              />
            </div>
          )}

          {!loading && messages && messages.length > 0 && filtered.length === 0 && (
            <div className="rounded-lg border border-dashed border-border">
              <EmptyState
                icon={<Search size={20} />}
                title={t("imap.emptyFiltered")}
                compact
              />
            </div>
          )}

          {filtered.map((m) => (
            <ImapMessageRow
              key={m.uid}
              message={m}
              expanded={suggestUid === m.uid}
              onToggleSuggest={() => setSuggestUid((cur) => (cur === m.uid ? null : m.uid))}
              onUse={onUse}
              onRecord={onRecord ? () => record(m) : undefined}
              recorded={!!recorded[m.uid]}
              busy={recordingUid === m.uid}
              onWritten={() => setRecorded((prev) => ({ ...prev, [m.uid]: true }))}
            />
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {messages ? (
              <>
                <Num numeric={false}>
                  {/* count 决定 messages 的单复数（按总数），shown/total 是显示值 */}
                  {t("imap.showing", {
                    count: messages.length,
                    shown: filtered.length,
                    total: messages.length,
                  })}
                </Num>
                {t("imap.hintWithRange", { range: rangeLabel })}
              </>
            ) : (
              t("imap.hint")
            )}
          </p>
          <Button variant="outline" onClick={onClose}>
            {t("common.cancel")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
