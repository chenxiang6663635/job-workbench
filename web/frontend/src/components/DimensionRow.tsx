import { useId } from "react";
import { ChevronDown } from "lucide-react";
import { Badge } from "./ui/badge";
import { abilityBadgeVariant, evidenceBadgeVariant } from "./badgeVariants";
import type { JobDetail } from "../api";
import { useTranslation } from "react-i18next";

/**
 * 解析卡的单个维度行（可展开看逐条命中依据）。
 * 此前是 div + onClick 的假按钮（无 aria-expanded、键盘不可达）——改为真 button；
 * 展开区必须放在 button **外面**（button 内嵌列表属无效 HTML，且会吞掉内容语义）。
 */
export default function DimensionRow({
  dimension,
  detail,
  expanded,
  onToggle,
}: {
  dimension: { name: string; score: number; max: number };
  detail: JobDetail["card"];
  expanded: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  const panelId = useId();
  const hits = detail?.dimensionsDetail[dimension.name]?.hits ?? [];
  const raw = detail?.dimensionsDetail[dimension.name]?.raw ?? [];

  return (
    <div className="rounded-xl border border-border/60 bg-background/40 transition-colors hover:border-primary/30">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="w-full cursor-pointer px-3 py-2 text-left"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ChevronDown
              size={14}
              className={`text-muted-foreground transition-transform ${expanded ? "rotate-180" : ""}`}
            />
            <span className="text-xs text-muted-foreground">{dimension.name}</span>
          </div>
          <span className="font-mono text-xs text-muted-foreground">
            {dimension.score} / {dimension.max}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary/60">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary/60 to-primary transition-all duration-700"
            style={{ width: `${(dimension.score / dimension.max) * 100}%` }}
          />
        </div>
      </button>

      {expanded && (
        <div id={panelId} className="space-y-2 border-t border-border px-3 py-3">
          {hits.length > 0 && (
            <ul className="space-y-1.5">
              {hits.map((h, i) => (
                <li key={i} className="flex items-start gap-2 text-xs">
                  <Badge variant={abilityBadgeVariant(h.level)} className="mt-0.5 shrink-0">
                    {h.level ?? t("dim.fallbackLevel")}
                  </Badge>
                  <span className="flex-1 text-muted-foreground">
                    {h.label}
                    {h.note && <span> — {h.note}</span>}
                  </span>
                  {h.evidence && (
                    <Badge variant={evidenceBadgeVariant(h.evidence)} className="shrink-0">
                      {h.evidence}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
          {raw.length > 0 && (
            <ul className="space-y-1.5">
              {raw.map((r, i) => (
                <li key={i} className="text-xs leading-relaxed text-muted-foreground">
                  {r}
                </li>
              ))}
            </ul>
          )}
          {!detail?.dimensionsDetail[dimension.name] && (
            <p className="text-xs text-muted-foreground">{t("dim.noEvidence")}</p>
          )}
        </div>
      )}
    </div>
  );
}
