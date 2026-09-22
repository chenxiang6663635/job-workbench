// 记录删除的窄接口（批 D 数据安全网）：**刻意不进 src/api.ts** —— 那个文件是
// 登记过水位的存量文件（只许变小），窄需求走窄模块（与 lib/bank.ts / lib/drill.ts
// 同一条理由）。落盘仍复用 `api.applyApproval`——写通道全站只有一条，不在这里另开。
//
// HTTP 封装用 lib/http.ts 的单一实现（H-1 批：四处副本合一，不再自带）。
import { requestJson } from "./http";

export type RecordPreview = {
  token: string;
  summary: string;
  diff: string[];
  expiresAt: number;
};

/** 五张从表（邮件 / 面试 / 联系人 / 宣讲会 / Offer）的删除预览。
 *  拿到令牌后由调用方走 `api.applyApproval` 落盘（写通道全站只有一条）。 */
export function previewDeleteRecord(
  kind: "mails" | "interviews" | "contacts" | "talks" | "offers",
  id: string
): Promise<RecordPreview> {
  return requestJson<RecordPreview>(
    `/progress/${kind}/preview-delete?id=${encodeURIComponent(id)}`
  );
}

/** 投递记录删除预览：差异表含「将解绑的关联记录」清单（记录保留、仅清外键）。 */
export function previewDeleteApplication(id: string): Promise<RecordPreview> {
  return requestJson<RecordPreview>(
    `/applications/preview-delete?id=${encodeURIComponent(id)}`
  );
}

/** 岗位目录删除预览：差异表逐条列目录内文件 + 关联投递保留提示。 */
export function previewDeleteJob(name: string): Promise<RecordPreview> {
  return requestJson<RecordPreview>(
    `/jobs/preview-delete?name=${encodeURIComponent(name)}`
  );
}

/** 岗位改名预览：目录名 `旧 → 新`；JD 首行标题可同步时一并列出。 */
export function previewRenameJob(
  name: string,
  company: string,
  role: string
): Promise<RecordPreview> {
  const params = new URLSearchParams({ name, company, role });
  return requestJson<RecordPreview>(`/jobs/preview-rename?${params.toString()}`);
}
