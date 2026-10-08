// 凭据清除端点客户端（#203 遗留）：**刻意不进 src/api.ts** —— 那个文件登记过
// 水位（486 行，只许变小），窄需求走窄模块（先例 lib/snapshotApi.ts）。
//
// 语义：清除即删——系统存储（Windows 凭据管理器）里的条目与工作区配置里的
// 引用一并删除；幂等（对没存过凭据的工作区调用同样返回 200）。
import type { ImapConfig } from "../api";
import { requestJson } from "./http";
import type { ProviderSettings } from "./providerApi";

export function clearImapCredential(): Promise<ImapConfig> {
  return requestJson<ImapConfig>("/imap/credential", { method: "DELETE" });
}

export function clearProviderCredential(): Promise<ProviderSettings> {
  return requestJson<ProviderSettings>("/provider/credential", { method: "DELETE" });
}
