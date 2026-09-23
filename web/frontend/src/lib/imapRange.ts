import type { TranslationKey } from "../i18n/locales/zh-CN";

// 时间窗选项：value 是给后端的 `since_days`（0 = 不限），labelKey 是展示文案的
// 翻译键——表必须在 `.ts` 模块里（带翻译 key 的模块级常量不能住在组件文件里，
// 那会让 ImapFetchDialog 越过 300 行的规模闸门）。
export const RANGE_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: "7", labelKey: "imap.range7" },
  { value: "30", labelKey: "imap.range30" },
  { value: "90", labelKey: "imap.range90" },
  { value: "0", labelKey: "imap.rangeAny" },
];

/** 某个天数对应的范围文案 key（0 = 不限）。 */
export function rangeLabelKey(sinceDays: number): TranslationKey | undefined {
  return RANGE_OPTIONS.find((o) => o.value === String(sinceDays))?.labelKey;
}
