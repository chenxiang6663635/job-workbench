import { useTranslation } from "react-i18next";
import { Check, ChevronRight, MailPlus, Sparkles } from "lucide-react";

import MailBody from "./MailBody";
import MailSuggestions from "./MailSuggestions";
import type { ImapMessage } from "../api";
import { formatMailDate } from "../lib/date";

/**
 * 拉取列表里的一封邮件（2026-09-25 从 `ImapFetchDialog` 拆出）。
 *
 * 拆出来有两个直接原因：
 * 1. 那个文件当时 299 行、贴着 300 行的规模闸门——条目几何（预览固定两行）
 *    没地方放；
 * 2. 条目高度原本随正文长短抖动（预览只按 140 字硬截 → 1~3 行），整列看起来
 *    参差——用户反馈的"邮件信息长度不一"就是这个。
 *
 * **状态一律留在父级**：`expanded`（同一时刻只开一行的解析建议）、`recorded`、
 * `busy`（防连点）都是列表级约束，搬进来就退化成"每行各管各的"。
 */
interface Props {
  message: ImapMessage;
  /** 解析建议面板是否展开 */
  expanded: boolean;
  onToggleSuggest: () => void;
  /** 走「解析 → 建议 → 确认」链路：正文交给「粘贴邮件更新」对话框 */
  onUse: (body: string) => void;
  /** 记入邮件台账；缺省 = 调用方没接这条链路，按钮不显示 */
  onRecord?: () => void;
  /** 已入台账（按钮就地变「已记录」） */
  recorded: boolean;
  /** 该条有记录请求在飞（父级统一判，防止连点落两行） */
  busy: boolean;
  /** 建议面板写入成功后的回调（父级据此把该条标成已记录） */
  onWritten: () => void;
}

export default function ImapMessageRow({
  message: m,
  expanded,
  onToggleSuggest,
  onUse,
  onRecord,
  recorded,
  busy,
  onWritten,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="rounded-lg border border-border bg-card/60 shadow-sm transition-colors hover:border-primary/40">
      <div className="group flex items-start gap-3 p-3">
        {/* 行主体：走「解析 → 建议 → 确认」链路（原行为不变） */}
        <button
          type="button"
          onClick={() => onUse(m.body)}
          title={t("imap.useThis")}
          className="min-w-0 flex-1 cursor-pointer text-left"
        >
          <p className="truncate text-sm font-medium text-foreground">
            {m.subject || t("imap.noSubject")}
          </p>
          <p className="mt-0.5 truncate text-xs text-muted-foreground">
            {m.from} · {formatMailDate(m.date)}
          </p>
          {/* 预览是原文（保留引用与签名）。`lines={2}` 与 140 字硬截并存：后者防
              DOM 过大，前者保证高度稳定。统一视图标注仍在，免得与建议卡的
              「已剥离引用」摘录被读成两份不一致的数据 */}
          <div className="mt-1.5">
            <MailBody text={m.body} truncated={m.truncated} limit={140} lines={2} />
          </div>
        </button>
        <div className="flex shrink-0 flex-col items-center gap-1.5">
          {/* 解析建议（批 9）：正文 / ICS → 候选事实，卡片逐条确认才写入 */}
          <button
            type="button"
            aria-label={t("suggest.title")}
            aria-expanded={expanded}
            title={t("suggest.title")}
            onClick={onToggleSuggest}
            className={
              expanded
                ? "cursor-pointer text-primary"
                : "cursor-pointer text-muted-foreground transition-colors hover:text-primary"
            }
          >
            <Sparkles size={16} />
          </button>
          {/* 记入邮件台账（批 4.5）：元数据直接落 mails.csv，不用再手打一遍 */}
          {onRecord && (
            <button
              type="button"
              disabled={recorded || busy}
              aria-label={t("imap.recordTitle")}
              title={t("imap.recordTitle")}
              onClick={onRecord}
              className="cursor-pointer text-muted-foreground transition-colors hover:text-primary disabled:cursor-default disabled:text-success"
            >
              {recorded ? <Check size={16} /> : <MailPlus size={16} />}
            </button>
          )}
          <ChevronRight
            size={16}
            className="text-muted-foreground transition-colors group-hover:text-primary"
          />
        </div>
      </div>
      {expanded && (
        <div className="px-3 pb-3">
          <MailSuggestions message={m} onOpenStatus={onUse} onWritten={onWritten} />
        </div>
      )}
    </div>
  );
}
