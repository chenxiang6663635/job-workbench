import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink, Loader2, Sparkles, X } from "lucide-react";
import { api, type Application, type ImapMessage, type Mail } from "../api";
import type { MailFact } from "../lib/domainTypes";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { planFactWrite } from "../lib/factWrites";
import { suggestFacts } from "../lib/mailFacts";
import { Button } from "./ui/button";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  message: ImapMessage;
  /** 成功写入后通知父级（例如刷新台账 / 记录态） */
  onWritten?: () => void;
  /** 出口：把正文交给既有「粘贴邮件更新」对话框（完整的手工通道） */
  onOpenStatus?: (body: string) => void;
}

const KIND_LABEL_KEYS: Record<MailFact["kind"], TranslationKey> = {
  时间: "suggest.kindTime",
  会议链接: "suggest.kindLink",
  阶段: "suggest.kindStage",
  公司岗位: "suggest.kindRecord",
};

/** 每条事实一张卡：确认写入 / 忽略。写入一律走既有链路（见 lib/factWrites）。 */
export default function MailSuggestions({ message, onWritten, onOpenStatus }: Props) {
  const { t } = useTranslation();
  const [facts, setFacts] = useState<MailFact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [ignored, setIgnored] = useState<Record<string, boolean>>({});
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setFacts(null);
    setDone({});
    setIgnored({});
    setAcked({});
    suggestFacts({ 原文: message.body || "", ics: message.calendar || "" })
      .then((r) => {
        if (alive) setFacts(r.facts);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [message.uid, message.body, message.calendar]);

  const keyOf = (fact: MailFact, index: number) => `${fact.kind}:${fact.value}:${index}`;

  const write = async (fact: MailFact, index: number) => {
    const plan = planFactWrite(fact, message);
    if (plan.kind === "blocked") {
      setError(t(plan.reasonKey));
      return;
    }
    const key = keyOf(fact, index);
    setBusy(key);
    setError(null);
    try {
      if (plan.kind === "mail") {
        await api.createMail(plan.body as Partial<Mail>);
      } else if (plan.kind === "application") {
        await api.updateApplication(plan.id, plan.body as Partial<Application>);
      } else {
        // 阶段：先用既有的只读接口取「原阶段」——服务端据此判断这条建议是否已过期，
        // 覆盖规则（终态不回退 / 拒信不覆盖 offer）也在服务端算，这里只做呈现。
        const result = await api.suggestStatus(message.body || "", plan.id);
        const match = result.matches.find((m) => m.id === plan.id);
        if (!match) throw new Error(t("suggest.recordGone"));
        if (!match.可覆盖) throw new Error(match.原因 || t("suggest.notAllowed"));
        await api.applyStatusSuggestion({
          id: plan.id,
          阶段: plan.stage,
          原阶段: match.当前阶段,
          依据: plan.evidence || undefined,
        });
      }
      setDone((prev) => ({ ...prev, [key]: t("suggest.done") }));
      onWritten?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const copy = (fact: MailFact, index: number) => {
    if (!navigator.clipboard?.writeText) return;
    navigator.clipboard
      .writeText(fact.value)
      .then(() => {
        setCopied(keyOf(fact, index));
        setTimeout(() => setCopied(null), 1500);
      })
      .catch(() => {
        /* 剪贴板不可用时静默：链接本身可选中复制 */
      });
  };

  const visible = (facts ?? []).filter((f, i) => !ignored[keyOf(f, i)]);

  return (
    <div
      role="group"
      aria-label={t("suggest.title")}
      className="mt-2 space-y-2 rounded-lg border border-border bg-background/60 p-3"
    >
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <Sparkles size={13} className="text-primary" />
        {t("suggest.title")}
      </p>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {facts === null && !error && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={13} className="animate-spin" /> {t("suggest.loading")}
        </p>
      )}

      {facts !== null && visible.length === 0 && (
        <p className="text-xs text-muted-foreground">{t("suggest.empty")}</p>
      )}

      {visible.map((fact) => {
        const index = (facts ?? []).indexOf(fact);
        const key = keyOf(fact, index);
        const low = fact.confidence === "low";
        const settled = done[key];
        return (
          <div
            key={key}
            role="group"
            aria-label={`${t(KIND_LABEL_KEYS[fact.kind])}: ${fact.value}`}
            className="rounded-md border border-border/70 bg-card/60 p-2.5 transition-opacity"
          >
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-xs">
                  <span className="font-medium text-foreground">{t(KIND_LABEL_KEYS[fact.kind])}</span>
                  <span className="min-w-0 truncate text-foreground" title={fact.value}>
                    {fact.value}
                  </span>
                  <span
                    className={
                      low
                        ? "rounded bg-warning/15 px-1.5 py-0.5 text-[10px] text-foreground"
                        : "rounded bg-secondary/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
                    }
                  >
                    {low ? t("suggest.low") : t("suggest.high")}
                  </span>
                </p>
                <p className="mt-1 truncate text-[11px] text-muted-foreground" title={fact.evidence}>
                  {fact.evidence}
                </p>
                {fact.note && <p className="mt-1 text-[11px] text-warning">{fact.note}</p>}

                {fact.kind === "会议链接" && !settled && (
                  <div className="mt-1.5 flex items-center gap-2 text-[11px]">
                    <a
                      href={fact.value}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      <ExternalLink size={12} /> {t("suggest.open")}
                    </a>
                    <button
                      type="button"
                      onClick={() => copy(fact, index)}
                      className="inline-flex cursor-pointer items-center gap-1 text-muted-foreground hover:text-primary"
                    >
                      <Copy size={12} />
                      {copied === key ? t("suggest.copied") : t("suggest.copy")}
                    </button>
                  </div>
                )}

                {low && !settled && (
                  <label className="mt-1.5 flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      className="h-3 w-3 accent-primary"
                      checked={!!acked[key]}
                      onChange={(e) =>
                        setAcked((prev) => ({ ...prev, [key]: e.target.checked }))
                      }
                    />
                    {t("suggest.ack")}
                  </label>
                )}
              </div>

              <div className="flex shrink-0 items-center gap-1.5">
                {settled ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-success">
                    <Check size={12} /> {settled}
                  </span>
                ) : (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 px-2 text-[11px]"
                      disabled={busy === key || (low && !acked[key])}
                      onClick={() => write(fact, index)}
                    >
                      {busy === key ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Check size={12} />
                      )}
                      {t("suggest.confirm")}
                    </Button>
                    <button
                      type="button"
                      aria-label={t("suggest.ignore")}
                      title={t("suggest.ignore")}
                      onClick={() => setIgnored((prev) => ({ ...prev, [key]: true }))}
                      className="cursor-pointer p-1 text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <X size={13} />
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        );
      })}

      {onOpenStatus && (
        <button
          type="button"
          onClick={() => onOpenStatus(message.body)}
          className="cursor-pointer text-[11px] text-muted-foreground underline-offset-2 hover:text-primary hover:underline"
        >
          {t("suggest.openFull")}
        </button>
      )}
    </div>
  );
}
