// 题库的新接口（目前只有「删除预览」）：**刻意不进 src/api.ts** —— 那个文件是
// 登记过水位的存量文件（1265 行，只许变小），窄需求走窄模块（与
// hooks/useWorkspaceSync.ts 同一条理由）。落盘仍复用 `api.applyApproval`——
// 写通道全站只有一条，不在这里另开。
//
// HTTP 封装用 lib/http.ts 的单一实现（H-1 批：四处副本合一，不再自带）。
import type { BankQuestion } from "../api";
import { requestJson } from "./http";

export type BankPreview = {
  token: string;
  summary: string;
  diff: string[];
  expiresAt: number;
};

/** 列表 / 抽题返回的行：领域层会附带 `due`（当日待复习）与 `reason`（为什么在队列里）。
 *  单独定义而不是往 api.ts 的 BankQuestion 里加字段——那个文件登记过水位（只许变小）。 */
export type BankRow = BankQuestion & { due?: boolean; reason?: string };

/** 删单题的预览：拿到令牌后由调用方走 `api.applyApproval` 落盘。 */
export function previewQuestionDelete(id: string): Promise<BankPreview> {
  return requestJson<BankPreview>(
    `/progress/questions/preview-delete?id=${encodeURIComponent(id)}`
  );
}

/** 改题的预览（1b）：参数名 -> CSV 中文字段名的映射与后端 `_UPDATE_FIELD_PARAMS`
 *  对齐；空值等同不改（领域层同口径）。2026-09-21 批次 B-2 从 api.ts 迁来
 *  （那里是登记过水位的存量文件，只许变小）并补齐「标签 / 备注」两个可改字段——
 *  改标签是错题标记的界面路径（加/去「错题」都走这里），此前界面只能改
 *  答案要点 / 状态 / 难度，而文档已宣称「界面改标签同效」（失实）。 */
export function previewQuestionUpdate(
  id: string,
  changes: {
    答案要点?: string;
    状态?: string;
    难度?: string;
    标签?: string;
    备注?: string;
  }
): Promise<BankPreview> {
  const params = new URLSearchParams({ id });
  if (changes.答案要点?.trim()) params.set("answer", changes.答案要点.trim());
  if (changes.状态?.trim()) params.set("status", changes.状态.trim());
  if (changes.难度?.trim()) params.set("difficulty", changes.难度.trim());
  if (changes.标签?.trim()) params.set("tags", changes.标签.trim());
  if (changes.备注?.trim()) params.set("note", changes.备注.trim());
  return requestJson<BankPreview>(
    `/progress/questions/preview-update?${params.toString()}`
  );
}

/** 新增题目的预览（1c）：字段给英文查询参数名（与后端 `_ADD_FIELD_PARAMS` 对齐）。
 *  空值不传——领域层视空值为未填（来源 / 状态的默认值由领域层补，预览表会列出）。 */
export function previewQuestionAdd(fields: {
  title: string;
  domain?: string;
  subject?: string;
  tags?: string;
  difficulty?: string;
  answer?: string;
  note?: string;
}): Promise<BankPreview> {
  const params = new URLSearchParams({ title: fields.title });
  if (fields.domain?.trim()) params.set("domain", fields.domain.trim());
  if (fields.subject?.trim()) params.set("subject", fields.subject.trim());
  if (fields.tags?.trim()) params.set("tags", fields.tags.trim());
  if (fields.difficulty?.trim()) params.set("difficulty", fields.difficulty.trim());
  if (fields.answer?.trim()) params.set("answer", fields.answer.trim());
  if (fields.note?.trim()) params.set("note", fields.note.trim());
  return requestJson<BankPreview>(
    `/progress/questions/preview-add?${params.toString()}`
  );
}
