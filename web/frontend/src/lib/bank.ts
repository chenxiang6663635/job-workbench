// 题库的新接口（目前只有「删除预览」）：**刻意不进 src/api.ts** —— 那个文件是
// 登记过水位的存量文件（1265 行，只许变小），窄需求走窄模块（与
// hooks/useWorkspaceSync.ts 同一条理由）。落盘仍复用 `api.applyApproval`——
// 写通道全站只有一条，不在这里另开。
//
// 代价是这里自带一份极薄的 GET 封装：ws 参数与错误本地化都照 api.ts 的口径，
// **不另立标准**（后端错误码 → `err.<code>` 文案，查不到才回落 detail）。
import i18n from "../i18n";
import { currentWorkspace } from "../api";

export type BankPreview = {
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

async function requestBank<T>(path: string): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const qs = currentWorkspace ? `${sep}ws=${encodeURIComponent(currentWorkspace)}` : "";
  const res = await fetch(`/api${path}${qs}`);
  if (!res.ok) throw new Error(humanize(await res.text(), res.status));
  return (await res.json()) as T;
}

/** 删单题的预览：拿到令牌后由调用方走 `api.applyApproval` 落盘。 */
export function previewQuestionDelete(id: string): Promise<BankPreview> {
  return requestBank<BankPreview>(
    `/progress/questions/preview-delete?id=${encodeURIComponent(id)}`
  );
}
