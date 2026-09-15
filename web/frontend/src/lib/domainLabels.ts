import type { TFunction } from "i18next";

/**
 * 领域枚举的显示层唯一入口。
 *
 * 背景：阶段 / 批次 / 评分档位这类枚举的「值」是工作区 CSV 与 CLI 输出的真值
 * （中文或中立 ID），**永不改动**——否则历史数据、脚本与命令行全部对不上账。
 * 英文界面的可读性靠这一层「值 → 当前语言文案」的映射解决，数据层零变化。
 *
 * 与通行做法一致（i18next context / Fluent select）：
 * - 未登记的值（新枚举、用户自填的轮次等）**原样返回**——显示退化为现状，
 *   绝不崩、绝不把 key 名漏给用户；
 * - CSV / CLI 的输出不经过这里，因此接口契约零变化；
 * - 「取值用的列名不翻，给人看的展示翻」——取值比较仍用原始值。
 */
export type DomainGroup =
  | "stage"
  | "batch"
  | "direction"
  | "tier"
  | "round"
  | "form"
  | "result"
  | "source"
  | "jobState";

/**
 * 键形如 `domain.<组>.<真值>`（扁平点号键，含中文段）。i18next v21+ 默认
 * `ignoreJSONStructure: true`——嵌套查找失败会按整串扁平键回查，本仓库的语言包
 * 全是这种扁平键（`nav.dashboard` 同款）。**依赖这个默认值**：若将来显式改掉，
 * 这一组键会静默退化（好在失败模式是「显示原值」，不是崩溃或漏 key 名）。
 */
export function domainLabel(group: DomainGroup, raw: string, t: TFunction): string {
  if (!raw) return raw;
  return t(`domain.${group}.${raw}` as never, { defaultValue: raw }) as string;
}
