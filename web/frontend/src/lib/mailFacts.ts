// 邮件解析接口（批 9）：**刻意不进 src/api.ts** —— 那个文件登记过水位（460 行，
// 只许变小），窄需求走窄模块（与 lib/bank.ts 同一条理由）。
//
// 只读：把已经拉到手的正文 / ICS 交给后端解释成候选事实。写回一律复用既有链路
// （api.createMail / api.updateApplication / api.applyStatusSuggestion），
// 这个模块不新增任何写通道。
import type { MailFactsResult } from "./domainTypes";
import { requestJson } from "./http";

/** 正文与 ICS 至少给一个；`id` = 用户手动指定的投递记录（站内信常不写公司名）。 */
export function suggestFacts(body: {
  原文: string;
  ics?: string;
  id?: string;
}): Promise<MailFactsResult> {
  return requestJson<MailFactsResult>("/imap/suggest-facts", {
    method: "POST",
    body,
  });
}
