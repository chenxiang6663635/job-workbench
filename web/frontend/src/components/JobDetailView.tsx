import { useTranslation } from "react-i18next";
import { ArrowLeft, FileText, Sparkles } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import DimensionRow from "./DimensionRow";
import GapPanel from "./GapPanel";
import { gateBadgeVariant, levelBadgeVariant } from "./badgeVariants";
import type { JobDetail } from "../api";

export default function JobDetailView({
  detail,
  expanded,
  onToggleDimension,
  onBack,
}: {
  detail: JobDetail;
  expanded: string | null;
  onToggleDimension: (name: string) => void;
  onBack: () => void;
}) {
  const { t } = useTranslation();
  const gates = detail.card?.hardGates;

  return (
    <div className="space-y-4">
      <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
        <ArrowLeft size={16} /> {t("job.backToPool")}
      </Button>

      <h2 className="text-lg font-semibold text-foreground">{detail.dir}</h2>

      {gates && (gates.items.length > 0 || gates.conclusion) && (
        <Card className="p-5">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-foreground">
              {t("job.hardGates")}
            </span>
            <Badge variant={gateBadgeVariant(gates.conclusion)}>
              {gates.conclusion ?? t("job.gatePending")}
            </Badge>
            {gates.reason && (
              <span className="text-xs text-destructive">
                {t("job.gateReason", { reason: gates.reason })}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {gates.items.map((it) => (
              <Badge key={it.key} variant="outline">
                {it.key}: {it.value || "—"}
              </Badge>
            ))}
          </div>
          {gates.details.length > 0 && (
            <ul className="mt-3 space-y-1.5 border-t border-border pt-3">
              {gates.details.map((d, i) => (
                <li key={i} className="text-xs leading-relaxed text-muted-foreground">
                  {d}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <FileText size={16} className="text-primary" /> {t("job.jdSource")}
          </div>
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg bg-background p-4 text-xs leading-relaxed text-muted-foreground">
            {detail.jd ?? t("job.jdMissing")}
          </pre>
        </Card>

        <Card className="p-5">
          <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
            <Sparkles size={16} className="text-primary" /> {t("job.parsedCard")}
          </div>

          {detail.card ? (
            <div className="space-y-4">
              <div className="flex items-baseline gap-3">
                <span className="bg-gradient-to-b from-white to-primary/70 bg-clip-text text-3xl font-semibold text-transparent">
                  {detail.card.total}
                </span>
                <span className="text-sm text-muted-foreground">/ 100</span>
                <Badge variant={levelBadgeVariant(detail.card.level)} className="ml-auto">
                  {detail.card.level}
                </Badge>
              </div>

              <div className="space-y-2">
                {detail.card.dimensions.map((d) => (
                  <DimensionRow
                    key={d.name}
                    dimension={d}
                    detail={detail.card}
                    expanded={expanded === d.name}
                    onToggle={() => onToggleDimension(d.name)}
                  />
                ))}
              </div>

              {detail.card.action && (
                <p className="rounded-lg bg-primary/10 px-3 py-2 text-xs text-primary">
                  {t("job.nextStep", { action: detail.card.action })}
                </p>
              )}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-6 text-center">
              <p className="text-sm text-muted-foreground">{t("job.cardMissing")}</p>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {t("job.cardEmptyHint1")}{" "}
                {/* 解析卡.md 是工作区里的真实文件名，不翻译。
                    用 {"…"} 包成字符串字面量而不是裸文本：裸文本一律按硬编码文案拦
                    （清单只放行字符串类命中），这样不翻的文件名也有个明确的写法。 */}
                <code className="text-muted-foreground">{"解析卡.md"}</code>{" "}
                {t("job.cardEmptyHint2")}
              </p>
            </div>
          )}

          {/* JD↔简历差距清单：只依赖 JD，未评分的岗位也能看——
              往往正是"还没评分但想先知道差在哪"的时刻 */}
          <div className="mt-4 rounded-xl border border-border bg-background/40 p-4">
            <GapPanel dir={detail.dir} />
          </div>
        </Card>
      </div>
    </div>
  );
}
