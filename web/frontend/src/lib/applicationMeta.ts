// 投递追踪表的元数据（H-2b 批自 pages/Applications.tsx 外移）：排序键、健康度
// 四态、阶段徽章样式、下钻状态与哨兵值——页面与表格组件共用，避免两处各写一份。
import type { TranslationKey } from "../i18n/locales/zh-CN";

// Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达
export const ALL = "__all__";
// 新建表单的「来源」是可选字段：空值也用哨兵表达（见「不填」选项）
export const NONE = "__none__";

// 静默阈值与后端 tracker.STALE_DAYS 一致；停留超过该值高亮
export const STALE_DAYS = 14;

export type SortKey = "next" | "score" | "stale" | "health";

// 健康度四态：颜色即严重度，具体理由放在 hover 的 title 里（给理由不给黑箱分数）
export const HEALTH_META: Record<string, { labelKey: TranslationKey; cls: string }> = {
  // 徽章小字（11px）要过 4.5:1——语义色只做底色，文字统一前景色：
  // warning 58% / primary 58% 直接当小字色在深底上只有 ~4.4（a11y 实测）。
  urgent: { labelKey: "app.healthUrgent", cls: "bg-destructive/15 text-foreground" },
  overdue: { labelKey: "app.healthOverdue", cls: "bg-warning/15 text-foreground" },
  stale: { labelKey: "app.healthStale", cls: "bg-primary/15 text-foreground" },
  ok: { labelKey: "app.healthOk", cls: "bg-secondary/60 text-muted-foreground" },
};

export type Drill = {
  stage?: string;
  direction?: string;
  batch?: string;
  active?: boolean;
  overdue?: boolean;
  dueWithin?: number;
  sort?: "health";
  focusId?: string;
};

// 页面初始状态：若来自看板下钻则读 sessionStorage，否则全空
export function readDrill(): Drill {
  try {
    const raw = sessionStorage.getItem("jobws_drill");
    if (!raw) return {};
    return JSON.parse(raw) as Drill;
  } catch {
    return {};
  }
}

export function stageStyle(stage: string) {
  if (stage === "已挂") return "bg-destructive/15 text-foreground";
  if (stage === "已放弃") return "bg-secondary/60 text-muted-foreground";
  // 我拒绝的 offer 是双向选择，不是失败——用成功色，区别于失败红
  // 小字徽章（11px）要过 4.5:1：语义色做底色，文字统一前景色——
  // success 55% / primary 58% 当小字色在深底上只有 ~4.4（a11y 实测三处命中）。
  if (stage === "我拒绝的 offer") return "bg-success/10 text-foreground";
  if (stage === "offer" || stage === "签约")
    return "bg-success/15 text-foreground";
  return "bg-primary/15 text-foreground";
}

// 值是 key 不是文案——模块级常量没法调 t()，渲染处再翻
export const SORT_LABELS: Record<SortKey, TranslationKey> = {
  next: "app.sortNext",
  score: "app.sortScore",
  stale: "app.sortStale",
  health: "app.sortHealth",
};
