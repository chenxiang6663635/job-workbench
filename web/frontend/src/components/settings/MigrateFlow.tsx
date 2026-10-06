import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRightLeft, Undo2 } from "lucide-react";
import { api, type MigrateActionResult, type MigratePlanView } from "../../api";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

/**
 * 数据根的**迁移流程块**（B2 引导式迁移，spec 决策 5 的「预览 → 确认」形状）：
 *
 * - 预览是纯读计划（清单 + 预检），blocked 是报告内容不是传输错误；
 * - 确认凭计划指纹（plan_token）复核——源数据在预览与确认之间变过会被拒；
 * - 在途事务（失败 / 中断）先给续跑与回滚的出路，再允许发起新迁移；
 * - 失败以事务报告呈现（源目录未受影响），可修完原因重试（差量续用已落位文件）。
 *
 * 两段式确认复用仓库的「预览 → 确认」协议形状（与快照还原同款纪律）：
 * 回滚与续跑都是先确认一步再执行。
 */
interface MigrateFlowProps {
  /** 诊断里的 migration_state != idle：在途（或失败待收尾）——先给出续跑/回滚出路 */
  migrationInFlight: boolean;
  /** 迁移切换 / 回滚后刷新系统路径（新数据根要如实反映到页面） */
  onReload?: () => void;
}

const formatBytes = (n: number | null | undefined): string => {
  if (n == null) return "—";
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
};

export default function MigrateFlow({
  migrationInFlight,
  onReload,
}: MigrateFlowProps) {
  const { t } = useTranslation();
  const [target, setTarget] = useState("");
  const [plan, setPlan] = useState<MigratePlanView | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [action, setAction] = useState<MigrateActionResult | null>(null);
  const [cardError, setCardError] = useState<string | null>(null);
  const [confirmRollback, setConfirmRollback] = useState(false);
  const [confirmResume, setConfirmResume] = useState(false);

  const runPreview = () => {
    setCardError(null);
    setPlan(null);
    setAction(null);
    setPlanLoading(true);
    api
      .dataRootMigratePreview(target)
      .then((view) => setPlan(view))
      .catch((e: Error) => setCardError(e.message))
      .finally(() => setPlanLoading(false));
  };

  const runApply = () => {
    if (!plan) return;
    setCardError(null);
    setApplying(true);
    api
      .dataRootMigrateApply(target, plan.plan_token)
      .then((result) => {
        setAction(result);
        setPlan(null);
        if (result.status === "done") onReload?.();
      })
      .catch((e: Error) => setCardError(e.message))
      .finally(() => setApplying(false));
  };

  const runRollback = () => {
    setCardError(null);
    setConfirmRollback(false);
    api
      .dataRootMigrateRollback(true)
      .then((result) => {
        setAction(result);
        onReload?.();
      })
      .catch((e: Error) => setCardError(e.message));
  };

  const runResume = () => {
    setCardError(null);
    setConfirmResume(false);
    api
      .dataRootMigrateResume(true)
      .then((result) => {
        setAction(result);
        onReload?.();
      })
      .catch((e: Error) => setCardError(e.message));
  };

  return (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium">
        <ArrowRightLeft size={14} className="text-primary" />
        {t("settings.dataLocMigrateLegend")}
      </p>
      <p className="text-[0.6875rem] leading-relaxed text-muted-foreground">
        {t("settings.dataLocMigrateDesc")}
      </p>

      {migrationInFlight && (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" className="h-7 px-3 text-xs"
                  onClick={() => setConfirmResume(true)}>
            {t("settings.dataLocResumeBtn")}
          </Button>
          <Button variant="outline" className="h-7 px-3 text-xs"
                  onClick={() => setConfirmRollback(true)}>
            <Undo2 size={14} /> {t("settings.dataLocRollbackBtn")}
          </Button>
        </div>
      )}
      {confirmResume && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs">{t("settings.dataLocResumeConfirm")}</span>
          <Button size="sm" className="h-7 px-3 text-xs" onClick={runResume}>
            {t("settings.dataLocConfirmBtn")}
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-3 text-xs"
                  onClick={() => setConfirmResume(false)}>
            {t("settings.dataLocCancelBtn")}
          </Button>
        </div>
      )}
      {confirmRollback && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs">{t("settings.dataLocRollbackConfirm")}</span>
          <Button size="sm" className="h-7 px-3 text-xs" onClick={runRollback}>
            {t("settings.dataLocConfirmBtn")}
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-3 text-xs"
                  onClick={() => setConfirmRollback(false)}>
            {t("settings.dataLocCancelBtn")}
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder={t("settings.dataLocTargetPlaceholder")}
          aria-label={t("settings.dataLocTargetLabel")}
          className="h-8 min-w-56 flex-1 font-mono text-xs"
        />
        <Button variant="outline" className="h-8 px-3 text-xs"
                disabled={!target.trim() || planLoading || applying}
                onClick={runPreview}>
          {planLoading
            ? t("settings.dataLocPreviewing")
            : t("settings.dataLocPreviewBtn")}
        </Button>
      </div>

      {plan && !plan.already_current && (
        <div className="space-y-1.5 rounded-md bg-muted/50 p-2.5">
          <p className="text-xs font-medium">
            {plan.ok
              ? t("settings.dataLocPlanOk")
              : t("settings.dataLocPlanBlocked")}
          </p>
          <p className="text-[0.6875rem] text-muted-foreground">
            {t("settings.dataLocPlanEntries", {
              count: plan.entries,
              bytes: formatBytes(plan.total_bytes),
            })}
            {" · "}
            {t("settings.dataLocPlanSkipped", { count: plan.skipped })}
          </p>
          <p className="break-all font-mono text-[0.6875rem] text-muted-foreground">
            {t("settings.dataLocPlanStaging", { path: plan.staging })}
          </p>
          {plan.free_bytes != null && (
            <p className="text-[0.6875rem] text-muted-foreground">
              {t("settings.dataLocPlanFree", { bytes: formatBytes(plan.free_bytes) })}
            </p>
          )}
          {plan.reasons.length > 0 && (
            <div>
              <p className="text-[0.6875rem] font-medium">
                {t("settings.dataLocReasonsTitle")}
              </p>
              <ul className="space-y-0.5">
                {plan.reasons.map((reason, i) => (
                  <li key={i} className="text-[0.6875rem] text-destructive">
                    · {reason.message}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.ok && (
            <Button size="sm" className="h-7 px-3 text-xs"
                    disabled={applying} onClick={runApply}>
              {applying
                ? t("settings.dataLocApplying")
                : t("settings.dataLocConfirmBtn")}
            </Button>
          )}
        </div>
      )}
      {plan?.already_current && (
        <p className="text-xs text-muted-foreground">
          {t("settings.dataLocNoop")}
        </p>
      )}

      {action?.status === "done" && (
        <p className="text-xs text-success">
          {t("settings.dataLocDone", { target: action.target_root ?? "" })}
        </p>
      )}
      {action?.status === "failed" && (
        <p className="text-xs text-destructive">
          {t("settings.dataLocFailed", { reason: action.reason ?? "" })}
        </p>
      )}
      {action?.status === "rolled-back" && (
        <p className="text-xs text-success">
          {t("settings.dataLocRolledBack", { target: action.source_root ?? "" })}
        </p>
      )}
      {cardError && <p className="text-xs text-destructive">{cardError}</p>}
    </div>
  );
}
