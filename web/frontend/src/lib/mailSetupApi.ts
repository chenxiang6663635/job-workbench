// 邮箱配置的两个只读端点客户端：**刻意不进 src/api.ts** —— 那个文件登记过水位
// （460 行，只许变小），窄需求走窄模块（先例 lib/snapshotApi.ts、lib/bank.ts）。
//
// HTTP 封装用 lib/http.ts 的单一实现（自动附 ?ws= 并自检工作区回显，见其注释）。
import type { MailProvider } from "./mailProviders";
import { requestJson } from "./http";

/** 服务商预设清单（真源在后端 jobws_core/mail_providers.py）。 */
export function listMailProviders(): Promise<MailProvider[]> {
  return requestJson<{ items: MailProvider[]; count: number }>("/mail/providers")
    .then((raw) => raw.items);
}

export interface MailFolders {
  folders: string[];
  count: number;
  server: string;
}

/**
 * 用已保存的凭证连一次，列出可选文件夹（只读 LIST）。
 *
 * 只在用户**点开候选**时调它：本项目没有后台预取——"点一次连一次"是既定纪律。
 */
export function listMailFolders(): Promise<MailFolders> {
  return requestJson<MailFolders>("/mail/folders", { method: "POST" });
}
