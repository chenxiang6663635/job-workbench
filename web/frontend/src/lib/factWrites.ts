// 「确认写入」的动作规划（批 9）：把候选事实翻译成**既有写路径**的调用参数。
//
// 纯函数：只做映射、不发请求（执行在 MailSuggestions 组件里）。这样三条纪律
// 能被单测钉住——
//   1. 每条事实只落一条既有链路（邮件台账 / 追踪表字段 / 两段式状态），不新建写通道；
//   2. 缺「对应记录」时给出 blocked 与原因，而不是悄悄写进错的记录；
//   3. 把握程度（confidence）不改变动作形态：它只决定界面要不要默认勾选。
import type { TranslationKey } from "../i18n/locales/zh-CN";
import type { MailFact } from "./domainTypes";

/** 规划动作所需的最小邮件元数据（与 ImapMessage 的结构兼容，便于直接传整条）。 */
export interface MailMeta {
  subject: string;
  from: string;
  date: string;
  messageId?: string;
}

export type FactWrite =
  | { kind: "mail"; body: Record<string, string> }
  | { kind: "application"; id: string; body: Record<string, string> }
  | { kind: "status"; id: string; stage: string; evidence: string }
  | { kind: "blocked"; reasonKey: TranslationKey };

function mailBody(meta: MailMeta, link: string): Record<string, string> {
  return {
    主题: meta.subject,
    发件人: meta.from,
    日期: meta.date,
    消息id: meta.messageId || "",
    关联记录: link,
  };
}

export function planFactWrite(fact: MailFact, meta: MailMeta): FactWrite {
  if (fact.kind === "会议链接") {
    return {
      kind: "mail",
      body: { ...mailBody(meta, fact.targetId), 会议链接: fact.value },
    };
  }
  if (fact.kind === "公司岗位") {
    // value 就是命中记录的 id：记台账时顺带关联上，省一次手工挑选
    return { kind: "mail", body: mailBody(meta, fact.value) };
  }
  if (fact.kind === "阶段") {
    if (!fact.targetId) return { kind: "blocked", reasonKey: "suggest.needRecord" };
    return { kind: "status", id: fact.targetId, stage: fact.value, evidence: fact.evidence };
  }
  if (fact.kind === "时间") {
    if (!fact.targetId) return { kind: "blocked", reasonKey: "suggest.needRecord" };
    // 追踪表的「下次动作日期」是 YYYY-MM-DD；带钟点的取值只取日期部分
    return {
      kind: "application",
      id: fact.targetId,
      body: { 下次动作日期: fact.value.slice(0, 10) },
    };
  }
  if (fact.kind === "截止" || fact.kind === "链接有效期") {
    if (!fact.targetId) return { kind: "blocked", reasonKey: "suggest.needRecord" };
    // 截止（要交东西）与链接有效期（链接会失效、要复制保存）走同一条既有写路径：
    // 日期进「下次动作日期」、动作短语（label）进「下次动作」——到点提醒读的就是
    // 这两个字段（看板的待办桶），写进去即自动获得提醒，不再另建提醒链路。
    // 两者的区别体现在 label 上（如「完成测评（链接即将失效）」）。
    return {
      kind: "application",
      id: fact.targetId,
      body: {
        下次动作日期: fact.value.slice(0, 10),
        下次动作: fact.label,
      },
    };
  }
  return { kind: "blocked", reasonKey: "suggest.unsupported" };
}
