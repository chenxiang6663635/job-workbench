import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import type { JobSummary } from "../api";

/** 档位 → Badge 语义色。此前是 levelColor() 手写 class 串 */
export function levelBadgeVariant(level: string | null) {
  if (!level) return "secondary" as const;
  if (level.includes("强烈")) return "success" as const;
  if (level.includes("建议投")) return "default" as const;
  if (level.includes("斟酌")) return "warning" as const;
  return "destructive" as const;
}

/** 能力分层 → Badge 语义色（Primary / Secondary / Weak） */
export function abilityBadgeVariant(level: string | null) {
  if (level === "Primary") return "default" as const;
  if (level === "Secondary") return "secondary" as const;
  if (level === "Weak") return "warning" as const;
  return "secondary" as const;
}

/** 证据标签 → Badge 语义色（精确 / 模糊 / 语义） */
export function evidenceBadgeVariant(ev: string | null) {
  if (ev === "精确") return "default" as const;
  if (ev === "模糊") return "warning" as const;
  if (ev === "语义") return "secondary" as const;
  return "outline" as const;
}

/** 岗位卡。此前整块 <button> 兼做卡片——现拆为 Card 容器 + 内部按钮（语义正确） */
export default function JobCard({
  job,
  onOpen,
}: {
  job: JobSummary;
  onOpen: () => void;
}) {
  return (
    <Card className="transition-all duration-300 ease-premium hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`${job.dir}，匹配度 ${job.score ?? "未评分"}`}
        className="w-full cursor-pointer p-5 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          {/* 卡片即按钮：内部不放 h3（heading 语义会被按钮吞掉），改由 aria-label 提供完整名称 */}
          <span className="text-sm font-semibold leading-snug text-foreground">
            {job.dir}
          </span>
          {job.score !== null && (
            <span className="bg-gradient-to-b from-white to-primary/70 bg-clip-text font-mono text-lg font-semibold text-transparent">
              {job.score}
            </span>
          )}
        </div>
        <div className="mt-3 flex items-center gap-2">
          {job.level ? (
            <Badge variant={levelBadgeVariant(job.level)}>{job.level}</Badge>
          ) : (
            <span className="text-xs text-muted-foreground">尚未评分</span>
          )}
          {job.hasJD && <span className="text-xs text-muted-foreground">JD 已存</span>}
        </div>
      </button>
    </Card>
  );
}
