import { useEffect, useState } from "react";
import { ChevronRight, Inbox, Loader2, RefreshCw, Search, X } from "lucide-react";
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

interface Props {
  onClose: () => void;
  /** 选定邮件后把正文交给「粘贴邮件更新」对话框预填（用户仍可编辑再解析） */
  onUse: (body: string) => void;
}

const RANGE_OPTIONS = [
  { value: "7", label: "最近 7 天" },
  { value: "30", label: "最近 30 天" },
  { value: "90", label: "最近 90 天" },
  { value: "0", label: "不限时间" },
];

/**
 * 从邮箱只读拉取邮件（服务端按时间窗搜索，最新在前），选一封交给
 * 「解析 → 建议 → 确认」流程。
 *
 * 打开本对话框 = 一次显式点击，此时才连接邮箱（没有后台连接/定时轮询）。
 * 拉取是 dry-run：不动邮箱、也不动追踪表；写回只发生在用户于下一步
 * 逐条确认之后。凭证与服务器配置在「设置」页。
 */
export default function ImapFetchDialog({ onClose, onUse }: Props) {
  const [messages, setMessages] = useState<ImapMessage[] | null>(null);
  const [server, setServer] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sinceDays, setSinceDays] = useState(30);
  const [query, setQuery] = useState("");

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .fetchImapMessages({ limit: 50, since_days: sinceDays })
      .then((r) => {
        setMessages(r.messages);
        setServer(r.server);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  // 切换时间窗即重新拉取（首次挂载也走这里）——用户改的是服务端搜索条件，
  // 不重拉的话列表与所选范围对不上
  useEffect(load, [sinceDays]);

  const q = query.trim().toLowerCase();
  const filtered = (messages ?? []).filter(
    (m) => !q || (m.subject + " " + m.from + " " + m.body).toLowerCase().includes(q)
  );
  const rangeLabel =
    RANGE_OPTIONS.find((o) => o.value === String(sinceDays))?.label ?? "";

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[82vh] w-full max-w-2xl flex-col gap-0 rounded-2xl p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Inbox size={16} className="text-primary" /> 从邮箱拉取邮件
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-3 overflow-y-auto p-5">
          <DialogDescription className="text-sm">
            只读拉取，最新在前；不会修改或删除任何邮件，也不会改动追踪表。
            {server && <span className="text-muted-foreground">（{server}）</span>}
          </DialogDescription>

          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={String(sinceDays)}
              onValueChange={(v) => setSinceDays(Number(v))}
            >
              <SelectTrigger className="h-8 w-32 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
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
                placeholder="按主题 / 发件人 / 正文筛掉无关邮件"
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
              <RefreshCw size={14} /> 重新拉取
            </Button>
          </div>

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {loading && (
            <p className="flex items-center gap-2 px-1 py-6 text-sm text-muted-foreground">
              <Loader2 size={15} className="animate-spin" /> 拉取中（只读连接）...
            </p>
          )}

          {!loading && messages && messages.length === 0 && (
            <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              {rangeLabel}内没有取到邮件。可以把时间范围放宽，或检查「设置」里
              的文件夹（如 INBOX）是否正确。
            </p>
          )}

          {!loading && messages && messages.length > 0 && filtered.length === 0 && (
            <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              筛掉之后没有剩下了——换个关键词，或清空筛选框。
            </p>
          )}

          {filtered.map((m) => (
            <button
              key={m.uid}
              type="button"
              onClick={() => onUse(m.body)}
              title="用这封邮件解析状态"
              className="group flex w-full items-start gap-3 rounded-xl border border-border bg-card/60 p-3 text-left shadow-sm transition-colors hover:border-primary/40 hover:bg-card"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">
                  {m.subject || "（无主题）"}
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {m.from} · {m.date}
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground/80">
                  {m.body.slice(0, 140)}
                  {m.body.length > 140 ? "…" : ""}
                </p>
              </div>
              <ChevronRight
                size={16}
                className="mt-0.5 shrink-0 text-muted-foreground/60 transition-colors group-hover:text-primary"
              />
            </button>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {messages
              ? `显示 ${filtered.length} / ${messages.length} 封（${rangeLabel}）· 点任意一封进入「解析 → 确认」`
              : "点任意一封进入「解析 → 建议 → 逐条确认」"}
          </p>
          <Button variant="outline" onClick={onClose}>
            关闭
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
