import { describe, expect, it } from "vitest";

import {
  PROVIDER_PRESETS,
  normalizeBaseUrl,
  presetIdForBaseUrl,
  validateBaseUrl,
} from "../../src/lib/providerPresets";

describe("PROVIDER_PRESETS", () => {
  it("每条都有 id 与文案 key，且 id 不重复", () => {
    const ids = PROVIDER_PRESETS.map((preset) => preset.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const preset of PROVIDER_PRESETS) {
      expect(preset.labelKey).toBeTruthy();
    }
  });

  it("除「自定义」外都给出 https 地址模板", () => {
    for (const preset of PROVIDER_PRESETS) {
      if (preset.id === "custom") continue;
      expect(preset.baseUrl.startsWith("https://")).toBe(true);
    }
  });

  it("自定义项与预设并列，且不带地址模板（逼用户自己想清楚填什么）", () => {
    const custom = PROVIDER_PRESETS.find((preset) => preset.id === "custom");
    expect(custom).toBeTruthy();
    expect(custom?.baseUrl).toBe("");
  });
});

describe("normalizeBaseUrl", () => {
  it("去首尾空白与末尾斜杠（保存前统一口径）", () => {
    expect(normalizeBaseUrl("  https://api.deepseek.com/v1/  ")).toBe(
      "https://api.deepseek.com/v1"
    );
    expect(normalizeBaseUrl("https://api.deepseek.com/v1///")).toBe(
      "https://api.deepseek.com/v1"
    );
  });

  it("空串与纯空白归一成空串", () => {
    expect(normalizeBaseUrl("")).toBe("");
    expect(normalizeBaseUrl("   ")).toBe("");
  });
});

describe("presetIdForBaseUrl", () => {
  it("按地址认出预设（尾斜杠不影响）", () => {
    expect(presetIdForBaseUrl("https://api.deepseek.com/v1")).toBe("deepseek");
    expect(presetIdForBaseUrl("https://api.deepseek.com/v1/")).toBe("deepseek");
    expect(presetIdForBaseUrl("https://api.moonshot.cn/v1")).toBe("kimi");
  });

  it("认不出就是「自定义」", () => {
    expect(presetIdForBaseUrl("https://my-gateway.example.com/v1")).toBe("custom");
    expect(presetIdForBaseUrl("")).toBe("custom");
  });
});

describe("validateBaseUrl", () => {
  it("没填时不提示（还不算错）", () => {
    expect(validateBaseUrl("")).toBeNull();
    expect(validateBaseUrl("   ")).toBeNull();
  });

  it("缺协议头 → 明确的提示 key（后端也会 422，但别让用户白跑一趟）", () => {
    expect(validateBaseUrl("api.deepseek.com/v1")).toBe("provider.hintNeedScheme");
  });

  it("通义填了原生地址 → 提示要兼容模式（与后端 base_url_hint 同一条）", () => {
    expect(validateBaseUrl("https://dashscope.aliyuncs.com/api/v1")).toBe(
      "provider.hintDashscope"
    );
    expect(
      validateBaseUrl("https://dashscope.aliyuncs.com/compatible-mode/v1")
    ).toBeNull();
  });

  it("把完整端点当 base_url 填 → 提示只填到版本段", () => {
    expect(validateBaseUrl("https://api.example.com/v1/chat/completions")).toBe(
      "provider.hintEndpointNotBase"
    );
  });

  it("普通地址保持安静（宁缺勿误报：很多网关路径就是自定义的）", () => {
    expect(validateBaseUrl("https://api.deepseek.com/v1")).toBeNull();
    expect(validateBaseUrl("https://my-gateway.example.com/openai/v1")).toBeNull();
  });
});
