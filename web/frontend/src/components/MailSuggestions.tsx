import { useTranslation } from "react-i18next";
import { Check, Copy, ExternalLink, Loader2, Sparkles, X } from "lucide-react";
import type { ImapMessage } from "../api";
import type { MailFact } from "../lib/domainTypes";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { useMailFacts } from "../hooks/useMailFacts";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
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

/** 每条事实一张卡：确认写入 / 忽略。写入一律走既有链路（见 hooks/useMailFacts）。 */
export default function MailSuggestions({ message, onWritten, onOpenStatus }: Props) {
  const { t } = useTranslation();
  const s = useMailFacts(message);

  const visible = (s.facts ?? []).filter((f, i) => !s.ignored[s.keyOf(f, i)]);

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

      {s.error && <ErrorBanner message={s.error} onClose={() => s.setError(null)} />}

      {s.facts === null && !s.error && (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 size={13} className="animate-spin" /> {t("suggest.loading")}
        </p>
      )}

      {s.facts !== null && visible.length === 0 && (
        <p className="text-xs text-muted-foreground">{t("suggest.empty")}</p>
      )}

      {visible.map((fact) => {
        const index = (s.facts ?? []).indexOf(fact);
        const key = s.keyOf(fact, index);
        const low = fact.confidence === "low";
        const settled = s.done[key];
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
                  <span className="font-medium text-foreground">
                    {t(KIND_LABEL_KEYS[fact.kind])}
                  </span>
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
                    {fact.source === "ai" ? ` · ${t("suggest.aiBadge")}` : ""}
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
                      onClick={() => s.copy(fact, index)}
                      className="inline-flex cursor-pointer items-center gap-1 text-muted-foreground hover:text-primary"
                    >
                      <Copy size={12} />
                      {s.copied === key ? t("suggest.copied") : t("suggest.copy")}
                    </button>
                  </div>
                )}

                {low && !settled && (
                  <label className="mt-1.5 flex cursor-pointer items-center gap-1.5 text-[11px] text-muted-foreground">
                    <input
                      type="checkbox"
                      className="h-3 w-3 accent-primary"
                      checked={!!s.acked[key]}
                      onChange={(e) => s.setAck(key, e.target.checked)}
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
                      disabled={s.busy === key || (low && !s.acked[key])}
                      onClick={() =>
                        s.write(fact, index).then((ok) => {
                          if (ok) onWritten?.();
                        })
                      }
                    >
                      {s.busy === key ? (
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
                      onClick={() => s.ignore(key)}
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

      {s.providerReady && (
        <div className="flex flex-wrap items-center gap-2 border-t border-border/70 pt-2 text-[11px]">
          <span className="text-muted-foreground">{t("suggest.aiTitle")}</span>
          <Input
            className="h-7 w-32 text-[11px]"
            placeholder={t("suggest.aiModelPlaceholder")}
            aria-label={t("suggest.aiModelLabel")}
            value={s.model}
            onChange={(e) => s.setModel(e.target.value)}
          />
          <Button
            size="sm"
            variant="outline"
            className="h-7 px-2 text-[11px]"
            disabled={s.aiBusy}
            onClick={s.runAi}
          >
            {s.aiBusy ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {t("suggest.aiRun")}
          </Button>
          {s.aiModel && (
            <span className="text-muted-foreground">
              {t("suggest.aiFrom", { model: s.aiModel })}
            </span>
          )}
          <span className="text-muted-foreground">{t("suggest.aiHint")}</span>
        </div>
      )}

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
