import { Loader2, Send } from "lucide-react";
import { Card } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { FAIL_TERMINAL, type ApplyState, type JobSummary } from "../api";

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

/**
 * 投递状态 → Badge 语义色。
 *
 * 「已终态」用中性色：终态里含「我拒绝的 offer」——那是双向选择不是失败，
 * 涂红等于把主动拒绝算成失败（与看板归因里单独统计它的口径相悖）。
 * 真正的失败阶段由下面 stage 文字单独标红。
 */
function applyStateBadgeVariant(state: ApplyState) {
  if (state === "流程中") return "default" as const;
  if (state === "已终态") return "secondary" as const;
  return "outline" as const;
}

/** 岗位卡。此前整块 <button> 兼做卡片——现拆为 Card 容器 + 内部按钮（语义正确） */
export default function JobCard({
  job,
  onOpen,
  onApply,
  applying = false,
  busy = false,
}: {
  job: JobSummary;
  onOpen: () => void;
  onApply?: () => void;
  applying?: boolean;
  // 别的卡片正在投递：本卡按钮也要禁用，否则能同时发起两个写请求
  busy?: boolean;
}) {
  return (
    <Card className="transition-all duration-300 ease-premium hover:-translate-y-1 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`${job.dir}，匹配度 ${job.score ?? "未评分"}，投递状态 ${job.applyState}`}
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
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {job.level ? (
            <Badge variant={levelBadgeVariant(job.level)}>{job.level}</Badge>
          ) : (
            <span className="text-xs text-muted-foreground">尚未评分</span>
          )}
          <Badge variant={applyStateBadgeVariant(job.applyState)}>
            {job.applyState}
          </Badge>
          {job.stage && (
            <span
              className={`text-xs ${
                FAIL_TERMINAL.includes(job.stage)
                  ? "text-destructive"
                  : "text-muted-foreground"
              }`}
            >
              {job.stage}
            </span>
          )}
          {job.hasJD && <span className="text-xs text-muted-foreground">JD 已存</span>}
        </div>
      </button>

      {/* 投递按钮放在主按钮之外：按钮嵌套按钮是非法 HTML，点击行为也会互相吞掉。
          流程中不给入口（同公司+岗位已有一条在跑）；已终态放行——「挂了再投一次」
          是合法数据，后端 find_duplicate 对终态行同样放行。 */}
      {onApply && job.applyState !== "流程中" && (
        <div className="flex items-center justify-between gap-2 border-t border-border px-5 py-3">
          <span className="text-xs text-muted-foreground">
            {job.applyState === "已终态"
              ? "再投会新建一条记录"
              : "投递后到追踪表继续跟进"}
          </span>
          <Button
            variant="outline"
            className="h-7 px-2.5 text-xs"
            onClick={onApply}
            disabled={applying || busy}
          >
            {applying ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Send size={12} />
            )}
            {applying
              ? "投递中…"
              : job.applyState === "已终态"
                ? "再投一次"
                : "一键投递"}
          </Button>
        </div>
      )}
    </Card>
  );
}
