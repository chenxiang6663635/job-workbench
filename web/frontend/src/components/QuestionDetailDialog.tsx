import { useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { api, type BankQuestion } from "../api";
import { BankPreviewCard } from "./BankPreviewCard";
import { QuestionDeleteButton } from "./QuestionDeleteButton";
import { Button } from "./ui/button";
import { Textarea } from "./ui/input";
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
import { Segmented } from "./ui/segmented";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

// 状态三态与难度档位：取值即工作区真实数据，不翻译（同列表徽章的约定）
const STATUSES = ["未看", "看过", "会了"];
const DIFFICULTIES = ["易", "中", "难"];
// 「未标」在 Radix Select 里不能再用空串（item 的 value 必须非空）；出参仍还原成 ""
const DIFFICULTY_NONE = "__none__";

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 break-words text-xs leading-relaxed text-foreground">{value || "—"}</p>
    </div>
  );
}

/** 只读区：全部字段摊开（答案要点**完整**显示，列表里是截断三行的）。 */
function ReadOnlyPanel({ item }: { item: BankQuestion }) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <Field label={t("bank.fieldDomain")} value={item.领域} />
        <Field label={t("bank.fieldSubject")} value={item.科目} />
        <Field label={t("bank.fieldTags")} value={item.标签} />
        <Field label={t("bank.fieldDifficulty")} value={item.难度} />
        <Field label={t("bank.fieldOrigin")} value={item.来源} />
        <Field label={t("bank.fieldStatus")} value={item.状态 || "未看"} />
        <Field label={t("bank.fieldCreated")} value={item.创建日期} />
        <Field label={t("bank.fieldReviewed")} value={item.最近复习} />
        <Field
          label={t("bank.fieldLinked")}
          value={[item.关联公司, item.关联岗位].filter(Boolean).join(" · ")}
        />
      </div>
      <div>
        <p className="text-[11px] text-muted-foreground">{t("bank.fieldAnswer")}</p>
        <p className="mt-1 whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2.5 text-xs leading-relaxed text-foreground">
          {item.答案要点 || t("bank.noAnswer")}
        </p>
      </div>
      {item.备注 && <Field label={t("bank.fieldNote")} value={item.备注} />}
    </section>
  );
}

// 差异确认卡已抽到 BankPreviewCard.tsx：导入与删除共用同一张卡，两处的"确认"
// 手感必须一致——删比改更不可逆，用户更该看清到底要删哪一行。

/** 编辑区：改答案要点 / 标三态 / 挑难度 → 预览 → 确认（两段式）。 */
function EditPanel({ item, onSaved }: { item: BankQuestion; onSaved: () => void }) {
  const { t } = useTranslation();
  const [answer, setAnswer] = useState(item.答案要点 || "");
  const [status, setStatus] = useState(item.状态 || "未看");
  const [difficulty, setDifficulty] = useState(item.难度 || "");
  const [preview, setPreview] = useState<{ token: string; summary: string; diff: string[] } | null>(
    null
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 只有「与原值不同且非空」的字段才进请求：空值等同不改（领域层同口径），
  // 所以界面上不假装支持"清空"——难度回退到未标这类操作不在本语义内。
  const changes: { 答案要点?: string; 状态?: string; 难度?: string } = {};
  if (answer.trim() && answer.trim() !== (item.答案要点 || "")) changes.答案要点 = answer.trim();
  if (status !== (item.状态 || "未看")) changes.状态 = status;
  if (difficulty && difficulty !== (item.难度 || "")) changes.难度 = difficulty;
  const hasChange = Object.keys(changes).length > 0;

  const onPreview = () => {
    setBusy(true);
    setError(null);
    api
      .previewQuestionUpdate(item.题目id, changes)
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
    <section className="mt-4 space-y-3 border-t border-border pt-4">
      <FormField label={t("bank.fieldAnswer")} hint={t("bank.editHint")}>
        <Textarea
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          rows={4}
          className="min-h-[96px] text-xs"
        />
      </FormField>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="mb-1 text-[11px] text-muted-foreground">{t("bank.fieldStatus")}</p>
          <Segmented
            value={status}
            onChange={setStatus}
            ariaLabel={t("bank.fieldStatus")}
            options={STATUSES.map((value) => ({ value, label: value }))}
          />
        </div>
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
              {/* 原值为空时才出现「未标」占位：难度一旦标过，本语义不支持改回空 */}
              {!item.难度 && (
                <SelectItem value={DIFFICULTY_NONE}>{t("bank.difficultyNone")}</SelectItem>
              )}
              {DIFFICULTIES.map((value) => (
                <SelectItem key={value} value={value}>
                  {value}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {preview ? (
        <BankPreviewCard
          summary={preview.summary}
          diff={preview.diff}
          busy={busy}
          onConfirm={onConfirm}
          onCancel={() => setPreview(null)}
        />
      ) : (
        <div className="flex items-center gap-3">
          <Button size="sm" onClick={onPreview} disabled={busy || !hasChange}>
            {busy ? t("bank.previewing") : t("bank.preview")}
          </Button>
          {!hasChange && (
            <span className="text-xs text-muted-foreground">{t("bank.noChange")}</span>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * 题目详情 + 就地维护（2026-09-18）：详情即编辑弹窗，形态对齐邮件台账。
 *
 * 上半只读（全字段 + 完整答案要点），下半编辑「答案要点 / 状态 / 难度」；
 * 提交后先看差异表再确认，落盘走全站唯一的 apply 通道。
 */
export function QuestionDetailDialog({
  item,
  onClose,
  onSaved,
}: {
  item: BankQuestion;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
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
            <DialogTitle className="pr-6 text-left text-base">
              {item.题目 || t("bank.detailTitle")}
            </DialogTitle>
            {/* Radix 要求 DialogContent 有可读描述，否则开发态会告警 */}
            <DialogDescription className="mt-0.5 text-left">
              {t("bank.detailDesc")}
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>
        <ReadOnlyPanel item={item} />
        <EditPanel item={item} onSaved={onSaved} />
        <QuestionDeleteButton id={item.题目id} onDeleted={onSaved} />
      </DialogContent>
    </Dialog>
  );
}
