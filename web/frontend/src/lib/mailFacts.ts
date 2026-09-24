// 邮件解析接口（批 9）：**刻意不进 src/api.ts** —— 那个文件登记过水位（460 行，
// 只许变小），窄需求走窄模块（与 lib/bank.ts 同一条理由）。
//
// 只读：把已经拉到手的正文 / ICS 交给后端解释成候选事实。写回一律复用既有链路
// （api.createMail / api.updateApplication / api.applyStatusSuggestion），
// 这个模块不新增任何写通道。
import type { MailFactsResult } from "./domainTypes";
import { requestJson } from "./http";

/**
 * 正文与 ICS 至少给一个；`id` = 用户手动指定的投递记录（站内信常不写公司名）。
 * `日期` = 这封邮件的发出日期：**时长表达**（「3 天内」）以它为基准——三天前
 * 收到的邮件今天再看应当已经过期，漏传就会按今天算、得出反向结论。
 */
export function suggestFacts(body: {
  原文: string;
  ics?: string;
  id?: string;
  日期?: string;
}): Promise<MailFactsResult> {
  return requestJson<MailFactsResult>("/imap/suggest-facts", {
    method: "POST",
    body,
  });
}

/**
 * 可选 AI 增强（BYOK）：同样只产建议、绝不写入。
 *
 * 模型名由用户填（与简历导入同一范式）——不替用户猜默认模型；
 * 返回的事实一律 confidence="low"，界面会强制核对后才允许写入。
 */
export function suggestFactsAi(body: {
  原文: string;
  ics?: string;
  model: string;
}): Promise<MailFactsResult & { model: string }> {
  return requestJson<MailFactsResult & { model: string }>("/imap/suggest-facts-ai", {
    method: "POST",
    body,
  });
}
