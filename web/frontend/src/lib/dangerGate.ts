/**
 * 危险操作门禁的**纯判定**（从 `components/ConfirmDangerDialog.tsx` 抽出来）。
 *
 * 抽出来的理由是可测：`phrase` / `name` 两档在当前产品里还没有接线对象（第一处用例是
 * 删除自定义主题的 `confirm` 档），只有把它做成纯函数才谈得上"先测后接"——等真接上
 * 高危动作时，门禁本身已经被钉住了。
 */
export type DangerLevel = "confirm" | "phrase" | "name";

/** 这一档是否需要用户手打内容；`confirm` 档不需要。 */
export function requiresTyping(level: DangerLevel): boolean {
  return level !== "confirm";
}

/**
 * 门禁是否放行。
 *
 * 判定口径：`confirm` 档直接放行；其余两档要求输入与 `challenge` **逐字符相等**
 * （trim 掉首尾空白，但保留大小写——确认词里大小写是有意义的信号，忽略它等于放松门禁）。
 * `challenge` 缺失时视为门禁坏掉，一律不放行（宁可拦住，也不能悄悄放行）。
 */
export function isGateOpen(
  level: DangerLevel,
  challenge: string | undefined,
  typed: string,
): boolean {
  if (!requiresTyping(level)) return true;
  if (!challenge) return false;
  return typed.trim() === challenge;
}

/** 是否处于"输入了但不匹配"的状态（用来决定要不要显示提示，而不是一打开就报错）。 */
export function isMismatch(
  level: DangerLevel,
  challenge: string | undefined,
  typed: string,
): boolean {
  if (!requiresTyping(level)) return false;
  if (!typed.trim()) return false;
  return !isGateOpen(level, challenge, typed);
}
