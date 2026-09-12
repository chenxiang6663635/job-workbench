import { useEffect, useState } from "react";
import { CheckCircle2, Inbox, Loader2, RefreshCw, X } from "lucide-react";
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
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  onClose: () => void;
  /** 选定邮件后把正文交给「粘贴邮件更新」对话框预填（用户仍可编辑再解析） */
  onUse: (body: string) => void;
}

/**
 * 从邮箱只读拉取最近邮件（最新在前），选一封交给「解析 → 建议 → 确认」流程。
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

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .fetchImapMessages({ limit: 20 })
      .then((r) => {
        setMessages(r.messages);
        setServer(r.server);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[80vh] w-full max-w-2xl flex-col gap-0 rounded-2xl p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Inbox size={16} className="text-primary" /> 从邮箱拉取最近邮件
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

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {loading && (
            <p className="flex items-center gap-2 px-1 py-6 text-sm text-muted-foreground">
              <Loader2 size={15} className="animate-spin" /> 拉取中（只读连接）...
            </p>
          )}

          {!loading && messages && messages.length === 0 && (
            <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
              没有取到邮件。如果邮箱确实有邮件，检查「设置」里的文件夹（如 INBOX）是否正确。
            </p>
          )}

          {messages?.map((m) => (
            <div key={m.uid} className="rounded-xl border border-border bg-card/60 p-3 shadow-sm">
              <div className="flex items-start justify-between gap-3">
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
                <Button
                  variant="outline"
                  className="h-7 shrink-0 px-2.5 text-xs"
                  onClick={() => onUse(m.body)}
                >
                  <CheckCircle2 size={12} /> 用这封
                </Button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            选一封后进入「解析 → 建议 → 逐条确认」——确认之前不会写任何数据
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={load} disabled={loading}>
              <RefreshCw size={14} /> 重新拉取
            </Button>
            <Button variant="outline" onClick={onClose}>
              关闭
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
