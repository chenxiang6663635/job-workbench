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
import { DRILL_KEY_IGNORE_SELECTOR, drillKeyAction } from "../lib/drillKeys";
import { BankPreviewCard } from "./BankPreviewCard";
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
  // 差异卡待确认期间锁住动作按钮：题卡内联之后不再被替换，不锁的话可以在确认框
  // 开着的时候继续自评 / 跳到下一题，确认的差异与眼前这道题就对不上了
  const locked = busy || preview !== null;

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

  // 键盘操作（2026-09-21）：一轮 5 道题纯鼠标要 16 次点击（抽题 + 每题 3 次），
  // 标错题再加——桌面端对着键盘练最省事。键位判定在 lib/drillKeys.ts（纯函数、
  // 有单测）；这里只把动作接到既有的预览 / 落盘函数上，**不绕写通道**。
  // 焦点在输入框 / 按钮上时不抢键（打字与浏览器自己"点"按钮都不该被劫）。
  // 刻意不写依赖数组：每次渲染重挂，闭包永远拿到最新的 current / preview / locked。
  useEffect(() => {
    if (!current) return;
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest(DRILL_KEY_IGNORE_SELECTOR)) return;
      const action = drillKeyAction(event, { locked, hasPreview: preview !== null });
      if (!action) return;
      event.preventDefault();
      if (action === "cancelPreview") setPreview(null);
      else if (action === "reveal") setRevealed(true);
      else if (action === "next") next();
      else if (action === "toggleWrong") toggleWrong();
      else grade(action.slice("grade:".length));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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

      {/* 题目卡**常驻**（2026-09-21）：此前 preview 一生效就把整张题卡换成差异卡，
          点完自评看不到刚答的题——而确认写入时恰恰最需要对着题面与答案再核一眼。
          差异卡改为内联在按钮组上方，确认语义与两段式流程一个字节都没动。 */}
      {current && (
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

          {preview && (
            <BankPreviewCard
              summary={preview.summary}
              diff={preview.diff}
              busy={busy}
              onConfirm={onConfirm}
              onCancel={() => setPreview(null)}
            />
          )}

          {/* 键位要写出来才有人知道（A-5）：不写的话这功能等于不存在 */}
          <p className="text-[11px] text-muted-foreground">{t("drill.kbdHint")}</p>

          <div className="mt-auto flex flex-wrap gap-2">
            <Button size="sm" onClick={() => grade("未看")} disabled={locked}>
              {t("drill.gradeTodo")}
            </Button>
            <Button size="sm" onClick={() => grade("看过")} disabled={locked}>
              {t("drill.gradeSeen")}
            </Button>
            <Button size="sm" onClick={() => grade("会了")} disabled={locked}>
              {t("drill.gradeKnown")}
            </Button>
            <Button variant="ghost" size="sm" onClick={toggleWrong} disabled={locked}>
              {t(wrongFlagged ? "drill.unmarkWrong" : "drill.markWrong")}
            </Button>
            <Button variant="ghost" size="sm" onClick={next} disabled={locked}>
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
