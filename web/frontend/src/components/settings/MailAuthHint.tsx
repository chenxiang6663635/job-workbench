import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ExternalLink } from "lucide-react";

import type { MailProvider } from "../../lib/mailProviders";
import { cn } from "../../lib/utils";

/**
 * 选中服务商后的就地引导（2026-09-24 从 ImapCard 拆出，为守住 300 行水位）。
 *
 * 文案按服务商换：163 / 126 / yeah.net 要求客户端先声明身份，Gmail 要应用专用密码，
 * 已知连不上的（Outlook 个人账号）**在这里直接说原因**——而不是让用户填完再撞一堵墙。
 * 调用方用 `key={provider.id}` 挂载，换服务商即重新展开（此刻他正需要这段文字）。
 */
interface MailAuthHintProps {
  provider: MailProvider;
  /** 文案 key：正常服务商是 authHintKey，不可用的是 unsupportedReasonKey */
  messageKey: string;
}

export default function MailAuthHint({ provider, messageKey }: MailAuthHintProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(true);

  return (
    <div className="space-y-1.5 rounded-lg border-l-[3px] border-warning/60 bg-muted/40 px-3 py-2">
      <button
        type="button"
        className="flex w-full items-center justify-between text-xs font-medium text-foreground"
        onClick={() => setOpen((value) => !value)}
      >
        {t("settings.imapAuthHintTitle")}
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          {t(messageKey)}
          {provider.docUrl && (
            <>
              {" "}
              <a
                className="inline-flex items-center gap-1 text-primary underline-offset-2 hover:underline"
                href={provider.docUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                <ExternalLink size={11} /> {t("settings.imapOpenGuide")}
              </a>
            </>
          )}
        </p>
      )}
    </div>
  );
}
