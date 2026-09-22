// 前端 HTTP 单一实现（H-1 批）：`requestJson` / `humanizeError` / 当前工作区的**唯一**一份。
// 此前这段在四处各抄了一份——api.ts（request 与 humanizeError）以及 lib/bank.ts /
// lib/drill.ts / lib/records.ts 三个窄模块自带的"极薄 GET 封装"；一处修四处改，
// 守卫一旦漂移，「静默展示别的工作区数据」类问题（issue #22 的原病）就会从某一份里漏过。
// 窄模块此后直接 import 本文件，不再自带副本。
import i18n from "../i18n";

/** 全局当前工作区（相对仓库根，如 personal）。空 = 用后端默认。 */
export let currentWorkspace = "";
export function setWorkspace(ws: string) {
  currentWorkspace = ws;
}

// 统一在工作区激活时给路径附加 ?ws=。库中 API 在 Web 场景必须显式传 workspace
// （tools/ 模块级 WORKSPACE 全局在并发下会互相覆盖），因此所有请求都带 ws。
export async function requestJson<T>(
  path: string,
  init?: { method?: string; body?: unknown }
): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const qs = currentWorkspace ? `${sep}ws=${encodeURIComponent(currentWorkspace)}` : "";
  const res = await fetch(`/api${path}${qs}`, {
    method: init?.method ?? "GET",
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    body: init?.body ? JSON.stringify(init.body) : undefined,
  });
  if (!res.ok) {
    throw new Error(humanizeError(await res.text(), res.status));
  }
  // 工作区自检（issue #22）：后端会回显本次实际服务的工作区。若与所选不一致就报错，
  // 而不是把别的工作区的数据当成你的数据展示出来——静默错位的后果比报错严重得多。
  // 两端都有值才比较：缺头（旧后端 / 跨源未暴露）时不误报。
  const served = res.headers.get("X-Jobws-Workspace");
  if (currentWorkspace && served && served !== currentWorkspace) {
    // 这条会直接显示给用户，所以走 i18n（这里是普通模块，用实例而非 useTranslation）
    throw new Error(
      i18n.t("api.workspaceMismatch", { requested: currentWorkspace, served })
    );
  }
  return res.json() as Promise<T>;
}

// 后端错误统一是 {"detail": "..."}；直接把原始 JSON 抛给 UI 会显示一坨花括号
// （端到端验证时就出现过 {"detail":"Method Not Allowed"}），这里抽成人话。
// 校验错误（422）的 detail 是数组，逐条拼接；非 JSON（纯文本 404 等）按原文返回。
export function humanizeError(raw: string, status: number): string {
  const fallback = i18n.t("api.requestFailed", { status });
  if (!raw.trim()) return fallback;
  try {
    const parsed = JSON.parse(raw) as {
      detail?: unknown;
      error_code?: unknown;
      error_params?: unknown;
    };
    // 后端在 detail 之外多给一个稳定的语义 code（加法改造，见 web/backend/apierror.py）：
    // 查得到本地化文案就用它，查不到回落 detail——绝不把 `err.xxx` 这样的 key 名显示给用户。
    if (typeof parsed?.error_code === "string" && parsed.error_code) {
      const key = `err.${parsed.error_code}`;
      if (i18n.exists(key)) {
        const params: Record<string, string> = {};
        for (const [k, v] of Object.entries(
          (parsed.error_params ?? {}) as Record<string, unknown>
        )) {
          params[k] = String(v);
        }
        return i18n.t(key, params);
      }
    }
    const detail = parsed?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      const parts = detail
        .map((item) => {
          const e = item as { msg?: string; loc?: unknown[] };
          const field = Array.isArray(e.loc) ? e.loc.slice(1).join(".") : "";
          return field && e.msg ? `${field}: ${e.msg}` : e.msg || JSON.stringify(item);
        })
        .filter(Boolean);
      if (parts.length) return parts.join("；");
    }
  } catch {
    // 不是 JSON：按原文返回
  }
  return raw.length > 300 ? `${raw.slice(0, 300)}…` : raw;
}
