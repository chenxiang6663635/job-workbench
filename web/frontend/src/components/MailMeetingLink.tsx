import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Video } from "lucide-react";

/**
 * 台账行里的会议链接（批 9）：打开 + 复制，自带短暂反馈。
 *
 * 单独成件的原因：`MailList.tsx` 是登记过水位的存量文件（只许变小），
 * 新能力走新文件；链路不变——值由解析建议卡经 `POST /api/progress/mails` 写入。
 */
export default function MailMeetingLink({ link }: { link: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copy = () => {
    if (!navigator.clipboard?.writeText) return;
    navigator.clipboard
      .writeText(link)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      })
      .catch(() => {
        /* 剪贴板不可用时静默：链接本身可选中复制 */
      });
  };

  return (
    <p className="mt-0.5 flex items-center gap-2 text-xs">
      <a
        href={link}
        target="_blank"
        rel="noreferrer"
        title={link}
        className="inline-flex min-w-0 items-center gap-1 truncate text-primary hover:underline"
      >
        <Video size={12} /> {t("mail.meetingLink")}
      </a>
      <button
        type="button"
        onClick={copy}
        aria-label={`${t("suggest.copy")}${t("mail.meetingLink")}`}
        className="inline-flex cursor-pointer items-center gap-1 text-muted-foreground hover:text-primary"
      >
        <Copy size={12} />
        {copied ? t("suggest.copied") : t("suggest.copy")}
      </button>
    </p>
  );
}
