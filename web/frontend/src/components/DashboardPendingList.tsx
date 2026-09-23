import { Flame } from "lucide-react";
import { useTranslation } from "react-i18next";

import type { PendingItem } from "../api";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { reasonLines } from "../lib/healthReasons";
import { Badge } from "./ui/badge";

// 健康度四态与追踪表同色同文案：颜色即严重度，理由整条列出（可核对优先）
const LEVEL_META: Record<
  string,
  { labelKey: TranslationKey; variant: "destructive" | "warning" | "default" }
> = {
  urgent: { labelKey: "app.healthUrgent", variant: "destructive" },
  overdue: { labelKey: "app.healthOverdue", variant: "warning" },
  stale: { labelKey: "app.healthStale", variant: "default" },
};

/**
 * 看板的「即将到来 / 待推进」清单（自 `pages/Dashboard.tsx` 拆出）。
 *
 * 拆出的理由是规模：Dashboard 是登记过的水位文件（只许变小），而这条清单是其中
 * 最自成一体的一块——只有它用到 LEVEL_META 与下钻。
 */
export function DashboardPendingList({
  pending,
  onDrill,
}: {
  pending: PendingItem[];
  /** 下钻到追踪表并聚焦该条：跳转协议留在 Dashboard（单一实现，别在这里再写一遍） */
  onDrill: (id: string) => void;
}) {
  const { t } = useTranslation();
  return (
    // min-w-0：truncate 行（nowrap）会把 grid 轨道顶宽 → 窄屏整页横向溢出（2026-09-23）
    <div className="min-w-0 rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
      <div className="mb-3 flex items-center gap-2">
        <Flame size={15} className="text-destructive" />
        <h2 className="text-sm font-semibold text-foreground">{t("dash.pendingTitle")}</h2>
        <span className="ml-auto text-[10px] text-muted-foreground">
          {t("dash.pendingSubtitle")}
        </span>
      </div>
      {pending.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("dash.pendingEmpty")}</p>
      ) : (
        <ul className="space-y-2">
          {pending.map((p) => {
            const meta = LEVEL_META[p.level] || LEVEL_META.stale;
            const lines = reasonLines(p.reasons, p.hints, t);
            return (
              <li key={p.id}>
                <button
                  onClick={() => onDrill(p.id)}
                  title={t("dash.pendingDrillHint")}
                  className="group w-full cursor-pointer rounded-lg bg-secondary/60 px-3 py-2 text-left transition-colors hover:bg-secondary"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate text-sm text-foreground transition-colors group-hover:text-primary">
                      {p.公司} · {p.岗位}
                    </span>
                    <Badge variant={meta.variant} className="shrink-0">
                      {t(meta.labelKey)}
                    </Badge>
                  </div>
                  {/* 理由整条亮出来：为什么该推进它，一目了然 */}
                  <p className="mt-1 truncate text-xs text-muted-foreground">
                    {lines.join(t("app.reasonJoiner"))}
                  </p>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
