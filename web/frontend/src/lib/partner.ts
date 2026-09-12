/**
 * Provider 推广入口与合作方预设 —— 全仓唯一一处定义。
 *
 * 只出现在设置页的 Provider 区块里（用户正好要在那里填 API Key）。三条纪律：
 *
 * 1. **这是推广（返佣）链接，界面上必须写明。** 藏在一个看起来像普通官网链接的
 *    按钮后面就是欺骗——本项目的红线是「不编造、不误导」，对链接同样适用。
 * 2. **它只是一个静态 href。** 不发请求、不带埋点、不回传任何信息，因此与设置页
 *    「无遥测、无上传」的承诺不冲突；也正因如此，它不需要也不应该有后端支持。
 * 3. **`url` 留空则该入口不渲染**——宁可不显示，也不要挂一个猜出来的链接。
 *
 * 关于合作方的审核：它在**公开仓库的配置文件**（.toml/.json/.yaml/.yml/.js/.ts/
 * .py/.go/.env）里搜索 `orcarouter`，写在 README 里不算。本文件是 .ts 且含有
 * `orcarouter`，因此满足；改动它时注意别把这条要求改没了。
 */
export interface ProviderReferral {
  /** 展示名，用于按钮文案 */
  name: string;
  /** 推广链接（含返佣标识）。空字符串 = 不显示该入口 */
  url: string;
  /** 一键填入设置页的 OpenAI 兼容端点 */
  presetBaseUrl?: string;
}

export const PROVIDER_REFERRAL: ProviderReferral | null = {
  name: "OrcaRouter",
  url: "https://www.orcarouter.ai/ref/ref_f34ad879f774bce8bc82",
  presetBaseUrl: "https://api.orcarouter.ai/v1",
};
