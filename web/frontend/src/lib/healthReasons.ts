import type { TFunction } from "i18next";
import type { ReasonHint } from "../api";
import { domainLabel } from "./domainLabels";

/**
 * 健康度理由的显示层（后端 hints 的前端半边）。
 *
 * hints[i] 有登记的 code 就按当前语言拼句（阶段名过 domainLabel）；
 * 未登记的 code / 旧后端 / 无 hints 时回落到后端原文——中文界面与原文一致。
 * 返回逐条文案数组，拼接用 `app.reasonJoiner`（中「；」英 "; "）。
 */
export function reasonLines(
  reasons: string[],
  hints: ReasonHint[] | undefined,
  t: TFunction,
): string[] {
  return reasons.map((r, i) => {
    const hint = hints?.[i];
    if (!hint) return r;
    const pp = hint.params;
    switch (hint.code) {
      case "deadline_passed":
        return t("health.deadlinePassed", { count: pp.days, days: pp.days });
      case "deadline_today":
        return t("health.deadlineToday");
      case "deadline_left":
        return t("health.deadlineLeft", { count: pp.days, days: pp.days });
      case "next_action_overdue":
        return pp.action
          ? t("health.nextActionOverdue", { count: pp.days, days: pp.days, action: pp.action })
          : t("health.nextActionOverdueNoAction", { count: pp.days, days: pp.days });
      case "stale_stage":
        return t("health.staleStage", {
          count: pp.days,
          days: pp.days,
          stage: domainLabel("stage", String(pp.stage), t),
        });
      default:
        return r;
    }
  });
}
