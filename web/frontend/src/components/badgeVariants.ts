/**
 * Badge 语义色映射（档位 / 能力分层 / 证据标签 / 硬门槛结论）。
 *
 * 独立成文件的原因：react-refresh/only-export-components 要求组件文件只导出
 * 组件——此前这些映射函数分别寄生在 JobCard / JobDetailView 里随组件导出，
 * CI 每次构建都报 react-refresh 警告。它们本来就不是组件，是「业务语义 →
 * Badge variant」的纯映射，放一起正好成为四个页面的单一事实源。
 */

/** 评分档位 → Badge 语义色。此前是 levelColor() 手写 class 串 */
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

/** 硬门槛三态 → Badge 语义色 */
export function gateBadgeVariant(conclusion: string | null) {
  if (conclusion === "通过") return "success" as const;
  if (conclusion === "不通过") return "destructive" as const;
  return "warning" as const;
}
