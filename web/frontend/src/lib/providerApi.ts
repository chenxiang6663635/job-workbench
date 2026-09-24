// Provider 端点客户端：**刻意不进 src/api.ts** —— 那个文件登记过水位（460 行，只许变小），
// 窄需求走窄模块（先例 lib/snapshotApi.ts、lib/mailSetupApi.ts）。
//
// HTTP 封装用 lib/http.ts 的单一实现（自动附 ?ws= 并自检工作区回显）。
import { requestJson } from "./http";

export interface ProviderSettings {
  base_url: string;
  /** 已脱敏 */
  api_key: string;
  hasKey: boolean;
  /** 默认模型名；空串表示没设（三处使用点会各自回退到手填） */
  model: string;
  /** base_url 的非阻断提示 key（`provider.hint*`），没有则 null */
  baseUrlHint: string | null;
}

export interface ProviderModels {
  ok: boolean;
  status: number;
  /** 服务端报的模型总数（可能大于 models.length） */
  modelCount: number;
  /** 最多 MODEL_LIST_LIMIT 个（后端截断，总数照报） */
  models: string[];
  truncated: boolean;
  /** 截断时的说明句（后端给的展示串，空串表示没有要说的） */
  hint: string;
}

export function getProviderSettings(): Promise<ProviderSettings> {
  return requestJson<ProviderSettings>("/provider");
}

/** 保存：`api_key` 传空则保留原值；`model` 传空是**清空**默认模型（两者语义不同）。 */
export function saveProvider(payload: {
  base_url: string;
  api_key: string;
  model: string;
}): Promise<ProviderSettings> {
  return requestJson<ProviderSettings>("/provider", { method: "POST", body: payload });
}

/**
 * 连通性测试：调 `{base_url}/models`。
 *
 * 失败**不阻塞保存**（这是刻意的：很多网关没实现 /models，但 chat 照样能用），
 * 所以调用方要把它当成"取模型清单 + 给一句人话"，而不是"能不能用"的唯一判据。
 */
export function testProvider(): Promise<ProviderModels> {
  return requestJson<ProviderModels>("/provider/test", { method: "POST" });
}
