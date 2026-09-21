// 记录删除的窄接口（批 D 数据安全网）：**刻意不进 src/api.ts** —— 那个文件是
// 登记过水位的存量文件（只许变小），窄需求走窄模块（与 lib/bank.ts / lib/drill.ts
// 同一条理由）。落盘仍复用 `api.applyApproval`——写通道全站只有一条，不在这里另开。
//
// 代价是这里自带一份极薄的 GET 封装：ws 参数与错误本地化都照 api.ts 的口径，
// **不另立标准**（后端错误码 → `err.<code>` 文案，查不到才回落 detail）。
// （封装与 bank.ts / drill.ts 的同类；H-1 批会一并收敛进 lib/http.ts。）
import i18n from "../i18n";
import { currentWorkspace } from "../api";

export type RecordPreview = {
  token: string;
  summary: string;
  diff: string[];
  expiresAt: number;
};

function humanize(raw: string, status: number): string {
  try {
    const parsed = JSON.parse(raw) as {
      detail?: string;
      error_code?: string;
      error_params?: Record<string, unknown>;
    };
    const code = typeof parsed.error_code === "string" ? parsed.error_code : "";
    if (code) {
      const key = `err.${code}`;
      if (i18n.exists(key)) {
        const params: Record<string, string> = {};
        for (const [k, v] of Object.entries(parsed.error_params ?? {})) {
          params[k] = String(v);
        }
        return i18n.t(key, params);
      }
    }
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail;
  } catch {
    /* 不是 JSON：回落原文 */
  }
  if (!raw.trim()) return i18n.t("api.requestFailed", { status });
  return raw.length > 300 ? `${raw.slice(0, 300)}…` : raw;
}

async function requestRecords<T>(path: string): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const qs = currentWorkspace ? `${sep}ws=${encodeURIComponent(currentWorkspace)}` : "";
  const res = await fetch(`/api${path}${qs}`);
  if (!res.ok) throw new Error(humanize(await res.text(), res.status));
  // 工作区自检（与 api.ts 的 issue #22 修复同口径）：后端会回显本次实际服务的工作区，
  // 与所选不一致就报错——静默展示**别的工作区**的数据，比报错严重得多。
  const served = res.headers.get("X-Jobws-Workspace");
  if (currentWorkspace && served && served !== currentWorkspace) {
    throw new Error(
      i18n.t("api.workspaceMismatch", { requested: currentWorkspace, served })
    );
  }
  return (await res.json()) as T;
}

/** 五张从表（邮件 / 面试 / 联系人 / 宣讲会 / Offer）的删除预览。
 *  拿到令牌后由调用方走 `api.applyApproval` 落盘（写通道全站只有一条）。 */
export function previewDeleteRecord(
  kind: "mails" | "interviews" | "contacts" | "talks" | "offers",
  id: string
): Promise<RecordPreview> {
  return requestRecords<RecordPreview>(
    `/progress/${kind}/preview-delete?id=${encodeURIComponent(id)}`
  );
}

/** 投递记录删除预览：差异表含「将解绑的关联记录」清单（记录保留、仅清外键）。 */
export function previewDeleteApplication(id: string): Promise<RecordPreview> {
  return requestRecords<RecordPreview>(
    `/applications/preview-delete?id=${encodeURIComponent(id)}`
  );
}
