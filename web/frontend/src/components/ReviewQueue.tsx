import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type BankQuestion } from "../api";
import {
  fetchDrill,
  previewMarkWrong,
  readDrillRound,
  saveDrillRound,
  tagsOf,
  WRONG_TAG,
  type DrillMode,
} from "../lib/drill";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { ErrorBanner } from "./ErrorBanner";
import { FormField } from "./FormField";
import { Input } from "./ui/input";

// 训练面板（2026-09-20）：抽题 → **盲答**（答案默认折叠）→ 展开对答案 → 自评三态 /
// 标错题 → 下一题。窄屏（390×844）优先：按钮单手够得着、长答案可滚动。
//
// 两条纪律：
// 1. **答案默认折叠**：答案就在旁边等于没练（"看一眼答案就算复习过"是最常见的自欺）；
// 2. **写操作全走两段式**：自评 = 改「状态」，标错题 = 改「标签」——都复用既有的
//    `question.update` 预览 + `/api/approvals/apply` 落盘，不新增写通道。
const MODES: DrillMode[] = ["due", "wrong", "random"];
const SIZES = [5, 10, 20];
/** 差异确认：与题库详情里的写入确认同一套手感（摘要 + 差异表 + 确认/取消）。 */
function DrillPreviewCard({
  summary,
  diff,
  busy,
  onConfirm,
  onCancel,
}: {
  summary: string;
  diff: string[];
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-2 p-3">
      <p className="text-sm font-medium text-foreground">{summary}</p>
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
        {diff.join("\n")}
      </pre>
      <div className="flex gap-2">
        <Button size="sm" onClick={onConfirm} disabled={busy}>
          {busy ? t("bank.writing") : t("bank.confirmWrite")}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
      </div>
    </Card>
  );
}

export default function ReviewQueue() {
  const { t } = useTranslation();
  // 懒初始化：storage 只在挂载时读一次（每帧读会让"刷新即回血"变成"刷新即重读"）
  const [saved] = useState(readDrillRound);
  const [mode, setMode] = useState<DrillMode>("due");
  const [size, setSize] = useState(5);
  const [keyword, setKeyword] = useState("");
  const [items, setItems] = useState<BankQuestion[]>(() => saved?.items ?? []);
  const [index, setIndex] = useState(() => saved?.index ?? 0);
  const [revealed, setRevealed] = useState(() => saved?.revealed ?? false);
  const [drawn, setDrawn] = useState(() => saved?.drawn ?? false);
  const [graded, setGraded] = useState(() => saved?.graded ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ token: string; summary: string; diff: string[] } | null>(
    null
  );

  // 令牌刻意**不**持久化：它十分钟过期，存下来只会让"确认"在 reload 之后报"令牌没了"
  useEffect(() => {
    saveDrillRound({ items, index, revealed, drawn, graded });
  }, [items, index, revealed, drawn, graded]);

  const current = items[index] as BankQuestion | undefined;
  const wrongFlagged = !!current && tagsOf(current.标签 || "").includes(WRONG_TAG);

  const runPreview = (promise: Promise<{ token: string; summary: string; diff: string[] }>) => {
    setBusy(true);
    setError(null);
    promise
      .then((r) => setPreview(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const onDraw = () => {
    setBusy(true);
    setError(null);
    setPreview(null);
    fetchDrill({ mode, n: size, keyword })
      .then((r) => {
        setItems(r.items);
        setIndex(0);
        setRevealed(false);
        setGraded(0);
        setDrawn(true);   // "抽过了但没命中"与"还没抽"是两种空态，文案不同
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  // 定义在使用之前（`onConfirm` 落盘成功后要调到下一题）：`no-use-before-define`
  // 是 eslint 的 error 级，且这条顺序在运行时也是真正需要的依赖方向。
  const next = () => {
    setRevealed(false);
    setIndex((currentIndex) => currentIndex + 1);
  };

  const onConfirm = () => {
    if (!preview) return;
    setBusy(true);
    setError(null);
    api
      .applyApproval(preview.token)
      .then(() => {
        setPreview(null);
        // 只数**真正落盘**的：取消 / 预览 400 / 落盘 409 都不该让"本轮写入 N 道"虚高
        setGraded((count) => count + 1);
        next();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const grade = (status: string) => {
    if (!current) return;
    if ((current.状态 || "未看") === status) {
      // 状态没变就没有可写的差异（领域层会以「这些字段的值没有变化」拒绝）——
      // 而「未看」在重练队列里是多数题的默认值，点它不该弹一条红色错误。直接过。
      next();
      return;
    }
    runPreview(api.previewQuestionUpdate(current.题目id, { 状态: status }));
  };

  const toggleWrong = () => {
    if (!current) return;
    runPreview(previewMarkWrong(current.题目id, !wrongFlagged));
  };

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <FormField label={t("drill.mode")}>
          <div className="inline-flex rounded-lg border border-border bg-surface-1 p-0.5">
            {MODES.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={
                  mode === value
                    ? "rounded-md bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary"
                    : "px-2.5 py-1 text-xs text-muted-foreground hover:text-foreground"
                }
              >
                {t(`drill.mode.${value}`)}
              </button>
            ))}
          </div>
        </FormField>
        <FormField label={t("drill.size")}>
          <select
            value={String(size)}
            onChange={(e) => setSize(Number(e.target.value))}
            className="h-9 rounded-lg border border-border bg-surface-1 px-2 text-xs text-foreground"
          >
            {SIZES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label={t("drill.keyword")}>
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            className="h-9 w-40 text-xs"
            aria-label={t("drill.keyword")}
          />
        </FormField>
        <Button size="sm" onClick={onDraw} disabled={busy}>
          {busy ? t("drill.starting") : t("drill.start")}
        </Button>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {items.length === 0 && !busy && (
        <Card className="space-y-1 p-4">
          {/* "还没抽"与"抽了没命中"分开说：后者说成"还没有抽题"会让人以为按钮坏了 */}
          <p className="text-sm font-medium text-foreground">
            {t(drawn ? "drill.noMatch" : "drill.empty")}
          </p>
          <p className="text-xs text-muted-foreground">
            {t(drawn ? "drill.noMatchHint" : "drill.emptyHint")}
          </p>
        </Card>
      )}

      {current && preview && (
        <DrillPreviewCard
          summary={preview.summary}
          diff={preview.diff}
          busy={busy}
          onConfirm={onConfirm}
          onCancel={() => setPreview(null)}
        />
      )}

      {current && !preview && (
        <Card className="flex flex-1 flex-col gap-3 p-4">
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            <span>
              {t("drill.progress", { index: index + 1, total: items.length })}
            </span>
            <span>
              {current.领域 || "—"} / {current.科目 || "—"}
            </span>
            <span>{current.状态 || "未看"}</span>
          </div>

          <p className="text-base leading-relaxed text-foreground">{current.题目}</p>

          {revealed ? (
            <p className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2.5 text-xs leading-relaxed text-foreground">
              {current.答案要点 || t("drill.answerMissing")}
            </p>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => setRevealed(true)}>
              {t("drill.reveal")}
            </Button>
          )}

          <div className="mt-auto flex flex-wrap gap-2">
            <Button size="sm" onClick={() => grade("未看")} disabled={busy}>
              {t("drill.gradeTodo")}
            </Button>
            <Button size="sm" onClick={() => grade("看过")} disabled={busy}>
              {t("drill.gradeSeen")}
            </Button>
            <Button size="sm" onClick={() => grade("会了")} disabled={busy}>
              {t("drill.gradeKnown")}
            </Button>
            <Button variant="ghost" size="sm" onClick={toggleWrong} disabled={busy}>
              {t(wrongFlagged ? "drill.unmarkWrong" : "drill.markWrong")}
            </Button>
            <Button variant="ghost" size="sm" onClick={next} disabled={busy}>
              {t("drill.next")}
            </Button>
          </div>
        </Card>
      )}

      {items.length > 0 && !current && (
        <Card className="space-y-1 p-4">
          <p className="text-sm font-medium text-foreground">{t("drill.done")}</p>
          <p className="text-xs text-muted-foreground">
            {t("drill.doneHint", { count: graded })}
          </p>
          <div className="pt-1">
            <Button size="sm" onClick={onDraw} disabled={busy}>
              {t("drill.restart")}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
