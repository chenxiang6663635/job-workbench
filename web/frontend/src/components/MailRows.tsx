import { Check, Copy, CornerDownRight, Pencil } from "lucide-react";
import { useTranslation } from "react-i18next";

import { MAIL_TAGS, type Mail } from "../api";
import { previewDeleteRecord } from "../lib/records";
import DeleteRecordButton from "./DeleteRecordButton";
import MailMeetingLink from "./MailMeetingLink";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

/**
 * 邮件台账的**行卡片**（2026-10-09 前端体验批从 MailList.tsx 原样搬出）。
 *
 * 搬出来的直接原因：MailList 是登记过水位的存量文件（只许变小），而这批要给
 * 长表加窗口化（行渲染 + 「显示更多」）——行先独立成件，窗口化才落得下。
 * 行内动作仍归 MailList（打标签 / 编辑 / 复制主题 / 关联跳转 / 删除后刷新），
 * 本组件只负责渲染，不自己取数、不自己持有数据状态。
 */
interface MailRowsProps {
  rows: Mail[];
  /** 已复制的邮件 id（复制主题后的对勾提示） */
  copied: string | null;
  onEdit: (row: Mail) => void;
  onTagChange: (id: string, tag: string) => void;
  onCopySubject: (row: Mail) => void;
  /** 关联记录可跳转：回追踪表并自动展开那条（复用看板 focusId 下钻） */
  onJumpToRecord: (id: string) => void;
  onReload: () => void;
}

export default function MailRows({
  rows,
  copied,
  onEdit,
  onTagChange,
  onCopySubject,
  onJumpToRecord,
  onReload,
}: MailRowsProps) {
  const { t } = useTranslation();

  return (
    <>
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
              {r.关联记录 && (
                <button
                  type="button"
                  onClick={() => onJumpToRecord(r.关联记录)}
                  title={t("mail.jumpToRecord")}
                  className="mt-0.5 inline-flex cursor-pointer items-center gap-1 text-xs text-primary hover:underline"
                >
                  <CornerDownRight size={12} />
                  {t("interview.related", { value: r.关联记录 })}
                </button>
              )}
              {/* 会议链接（批 9）：解析建议卡写进来的入会地址——台账里也能打开 / 复制 */}
              {r.会议链接 && <MailMeetingLink link={r.会议链接} />}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Select value={r.标签} onValueChange={(v) => onTagChange(r.邮件id, v)}>
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
                onClick={() => onEdit(r)}
              >
                <Pencil size={13} />
              </Button>
              <DeleteRecordButton
                preview={() => previewDeleteRecord("mails", r.邮件id)}
                onDeleted={onReload}
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
                  onClick={() => onCopySubject(r)}
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
    </>
  );
}
