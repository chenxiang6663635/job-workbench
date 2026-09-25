import { useTranslation } from "react-i18next";

/**
 * 邮件正文的统一视图 + **三态标注**（2026-09-24「正文口径」笔）。
 *
 * 同一封邮件在三个环节被清洗到不同粒度，而界面上原本一处说明都没有：
 *   1. 拉取列表预览——原文，硬截 140 字；
 *   2. 点开后预填进状态对话框——原文（**保留引用与签名**），后端上限 4000 字；
 *   3. ✨解析建议的「出处」——**先剥掉引用与签名**再摘，每条 120 字。
 * 用户看到"两处正文不一样"时的第一反应是"数据丢了"。这个组件把"为什么不一样"
 * 写在正文旁边，而不是留给用户猜。
 *
 * `variant` 是语义、不是样式：`original` 表示与收到的邮件一致，`excerpt` 表示
 * "这段只为解析服务，别拿它当原文用"。
 */
interface MailBodyProps {
  text: string;
  /** 后端标注的截断（`BODY.PEEK[]<0.N>` 顶到上限）：大附件邮件只拉回前段 */
  truncated?: boolean;
  variant?: "original" | "excerpt";
  /** 预览字符数；不传则显示全文 */
  limit?: number;
  /**
   * 固定显示行数（列表预览用）。字面量映射是刻意的：Tailwind 的 JIT 只认源文件里
   * 出现过的类名，拼字符串（`line-clamp-${n}`）会在构建时被丢。
   */
  lines?: 1 | 2 | 3;
  /** 紧凑形态（建议卡）：徽章与正文同行，不额外占一行 */
  compact?: boolean;
}

const CLAMP_CLASS: Record<number, string> = {
  1: "line-clamp-1",
  2: "line-clamp-2",
  3: "line-clamp-3",
};

export default function MailBody({
  text,
  truncated = false,
  variant = "original",
  limit,
  lines,
  compact = false,
}: MailBodyProps) {
  const { t } = useTranslation();
  const cropped = Boolean(limit && text.length > limit);
  const shown = cropped ? `${text.slice(0, limit as number)}…` : text;
  const badge = variant === "excerpt" ? t("mail.bodyExcerpt") : t("mail.bodyOriginal");

  if (compact) {
    // 徽章与正文各自成节点：正文必须保持"就是那段文本"——塞进同一个节点会让
    // 按文本精确匹配的断言（与读屏）拿到 "Excerpt面试邀请" 这种拼接结果
    return (
      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <span className="shrink-0 rounded border border-border px-1 py-0.5 text-[10px]">
          {badge}
        </span>
        <span className="min-w-0 truncate" title={text}>
          {shown}
        </span>
      </p>
    );
  }

  return (
    <div className="space-y-1">
      <p className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
        <span className="rounded border border-border px-1.5 py-0.5">{badge}</span>
        {(truncated || cropped) && (
          <span className="rounded border border-border px-1.5 py-0.5">
            {t("mail.bodyTruncated", { n: text.length })}
          </span>
        )}
        <span>
          {variant === "excerpt" ? t("mail.bodyExcerptNote") : t("mail.bodyOriginalNote")}
        </span>
      </p>
      <p
        className={
          "whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground" +
          (lines ? ` ${CLAMP_CLASS[lines]}` : "")
        }
      >
        {shown}
      </p>
    </div>
  );
}
