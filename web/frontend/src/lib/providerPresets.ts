// Provider 服务商预设与 base_url 的**非阻断**校验（纯函数，无 I/O —— 单测不需要 jsdom）。
//
// 地址模板是"起点"不是承诺：它对着各家官方文档核过，但这类域名会变（通义的
// `compatible-mode` 就是最常踩的一个），所以每次保存后「测试连接」才是判据。
//
// 校验刻意不阻断保存：Open WebUI 的经验是「验证失败 ≠ 不兼容」——很多网关的路径
// 就是自定义的，误报会让人白改一趟。这里只报两种确证过的坑（与后端
// `provider.base_url_hint` 同一口径，两边不该各有一套）。

export interface ProviderPreset {
  id: string;
  labelKey: string;
  /** 地址模板；「自定义」为空串（逼用户自己想清楚填什么） */
  baseUrl: string;
  /** 该选项的注意点（i18n key）；没有则空串 */
  noteKey: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: "deepseek",
    labelKey: "providerPreset.deepseek",
    baseUrl: "https://api.deepseek.com/v1",
    noteKey: "",
  },
  {
    id: "zhipu",
    labelKey: "providerPreset.zhipu",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    noteKey: "",
  },
  {
    id: "dashscope",
    labelKey: "providerPreset.dashscope",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    noteKey: "provider.hintDashscope",
  },
  {
    id: "kimi",
    labelKey: "providerPreset.kimi",
    baseUrl: "https://api.moonshot.cn/v1",
    noteKey: "",
  },
  {
    id: "siliconflow",
    labelKey: "providerPreset.siliconflow",
    baseUrl: "https://api.siliconflow.cn/v1",
    noteKey: "",
  },
  {
    id: "openai",
    labelKey: "providerPreset.openai",
    baseUrl: "https://api.openai.com/v1",
    noteKey: "",
  },
  {
    id: "custom",
    labelKey: "providerPreset.custom",
    baseUrl: "",
    noteKey: "providerPreset.customNote",
  },
];

/** 规范化：去首尾空白与末尾斜杠（保存前统一口径，避免 `/v1/` 与 `/v1` 被当成两个）。 */
export function normalizeBaseUrl(baseUrl: string): string {
  return (baseUrl ?? "").trim().replace(/\/+$/, "");
}

/** 从地址反查预设 id（用于回显"现在填的是哪一家"）；认不出就是「自定义」。 */
export function presetIdForBaseUrl(baseUrl: string): string {
  const normalized = normalizeBaseUrl(baseUrl);
  if (!normalized) return "custom";
  const hit = PROVIDER_PRESETS.find(
    (preset) => preset.baseUrl !== "" && normalizeBaseUrl(preset.baseUrl) === normalized
  );
  return hit ? hit.id : "custom";
}

/**
 * 非阻断校验：返回提示的 i18n key，没问题返回 null。
 *
 * 空串返回 null——还没填不算错，别在用户刚开始打字时就报红。
 */
export function validateBaseUrl(baseUrl: string): string | null {
  const raw = (baseUrl ?? "").trim();
  if (!raw) return null;
  const url = raw.toLowerCase();
  if (!url.includes("://")) return "provider.hintNeedScheme";
  if (url.includes("dashscope.aliyuncs.com") && !url.includes("compatible-mode")) {
    return "provider.hintDashscope";
  }
  if (url.includes("/chat/completions")) return "provider.hintEndpointNotBase";
  return null;
}
