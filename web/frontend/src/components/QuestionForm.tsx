import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";

import { api } from "../api";
import { previewQuestionAdd } from "../lib/bank";
import { BankPreviewCard } from "./BankPreviewCard";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { ErrorBanner } from "./ErrorBanner";
import { FormField } from "./FormField";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

// 难度档位取值即工作区真实数据，不翻译（与详情弹窗、列表徽章同一套约定）
const DIFFICULTIES = ["易", "中", "难"];
// 「未标」在 Radix Select 里不能再用空串（item 的 value 必须非空）；出参仍还原成 ""
const DIFFICULTY_NONE = "__none__";

/**
 * 新增题目（2026-09-21 批次 B-1）：此前界面只能改已有的题，加题得去命令行——
 * 空态文案把用户往 CLI 推。本表单只收「自拟」场景真正需要的字段：来源固定
 * `自拟`、状态固定 `未看`（都由领域层补默认值，预览表里如实列出）；关联公司 /
 * 岗位属于"被问过的题"，那条路走导入，不在这里重复。
 *
 * 两段式与全站同构：预览 → 差异表 → 确认 → `POST /api/approvals/apply`
 * （写通道只有一条；「已存在同名同领域的题」这类拒绝在预览段就发生）。
 */
export function QuestionForm({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("");
  const [subject, setSubject] = useState("");
  const [tags, setTags] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [answer, setAnswer] = useState("");
  const [note, setNote] = useState("");
  const [preview, setPreview] = useState<{ token: string; summary: string; diff: string[] } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = title.trim().length > 0;

  const onPreview = () => {
    setBusy(true);
    setError(null);
    previewQuestionAdd({ title, domain, subject, tags, difficulty, answer, note })
      .then((r) => setPreview({ token: r.token, summary: r.summary, diff: r.diff }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onConfirm = () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    // 两段式的第二步：凭令牌落盘（与命令行 / MCP 同源，冲突与过期由服务端拒绝）
    api
      .applyApproval(preview.token)
      .then(() => onSaved())
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="max-h-[88vh] w-full max-w-2xl overflow-y-auto rounded-lg p-6">
        <DialogHeader className="mb-4 flex-row items-center justify-between space-y-0">
          <div>
            <DialogTitle className="pr-6 text-left text-base">{t("bank.addTitle")}</DialogTitle>
            {/* Radix 要求 DialogContent 有可读描述，否则开发态会告警 */}
            <DialogDescription className="mt-0.5 text-left">
              {t("bank.addDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <section className="space-y-3">
          <FormField label={t("bank.fieldTitle")}>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} className="text-xs" />
          </FormField>
          <div className="grid grid-cols-2 gap-4">
            <FormField label={t("bank.fieldDomain")}>
              <Input value={domain} onChange={(e) => setDomain(e.target.value)} className="text-xs" />
            </FormField>
            <FormField label={t("bank.fieldSubject")}>
              <Input
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                className="text-xs"
              />
            </FormField>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <FormField label={t("bank.fieldTags")}>
              <Input value={tags} onChange={(e) => setTags(e.target.value)} className="text-xs" />
            </FormField>
            <div>
              <p className="mb-1 text-[11px] text-muted-foreground">{t("bank.fieldDifficulty")}</p>
              <Select
                value={difficulty || DIFFICULTY_NONE}
                onValueChange={(value) => setDifficulty(value === DIFFICULTY_NONE ? "" : value)}
              >
                <SelectTrigger className="h-9 w-full text-xs" aria-label={t("bank.fieldDifficulty")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={DIFFICULTY_NONE}>{t("bank.difficultyNone")}</SelectItem>
                  {DIFFICULTIES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <FormField label={t("bank.fieldAnswer")}>
            <Textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              rows={4}
              className="min-h-[96px] text-xs"
            />
          </FormField>
          <FormField label={t("bank.fieldNote")}>
            <Input value={note} onChange={(e) => setNote(e.target.value)} className="text-xs" />
          </FormField>
        </section>

        {error && (
          <div className="mt-3">
            <ErrorBanner message={error} onClose={() => setError(null)} />
          </div>
        )}

        {preview ? (
          <div className="mt-4">
            <BankPreviewCard
              summary={preview.summary}
              diff={preview.diff}
              busy={busy}
              confirmLabel={t("bank.confirmAdd")}
              onConfirm={onConfirm}
              onCancel={() => setPreview(null)}
            />
          </div>
        ) : (
          <div className="mt-4 flex items-center gap-3 border-t border-border pt-4">
            <Button size="sm" onClick={onPreview} disabled={busy || !canSubmit}>
              {busy ? t("bank.previewing") : t("bank.previewAdd")}
            </Button>
            {!canSubmit && (
              <span className="text-xs text-muted-foreground">{t("bank.addNeedTitle")}</span>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
