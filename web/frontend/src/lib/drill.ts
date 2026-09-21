// 训练面板的数据接口（抽题 + 标错题预览）：**刻意不进 src/api.ts** —— 那个文件
// 是登记过水位的存量文件（1265 行，只许变小），窄需求走窄模块（与
// hooks/useWorkspaceSync.ts 同一条理由）。落盘仍复用 `api.applyApproval`——
// 写通道全站只有一条，不在这里另开。
//
// 因此这里自带一份极薄的 GET 封装：ws 参数与错误本地化都照 api.ts 的口径，
// **不另立标准**（后端错误码 → `err.<code>` 文案，查不到才回落 detail）。
import i18n from "../i18n";
import { currentWorkspace } from "../api";
import type { BankRow } from "./bank";

// 数据值，不翻译：标签里的「错题」就是 CSV 里的真实取值（与 due / wrong 的口径同源）。
// 拿翻译串去比会随界面语言漂移——中文界面标的错题，英文界面就认不出来了。
export const WRONG_TAG = "错题";

// 标签判定与领域层同源（`question_review.split_tags` 的分隔符集合）。用
// `includes("错题")` 会把「错题本」「高频错题」误判成"已标错题"，于是请求与实际
// 相反（on=0 → 400「不在错题本里」），而那题就从面板里**永远标不上**。
const TAG_SPLIT_RE = /[,，、;；\s]+/;

export function tagsOf(text: string): string[] {
  return (text || "").split(TAG_SPLIT_RE).filter(Boolean);
}

// 本轮状态落 sessionStorage：自评 / 标错题会写 questions.csv，而工作区指纹刷新
// （App 级 useWorkspaceSync）会整页 reload——不存的话每写一题，本轮抽到的题、
// 进度与折叠状态全丢，"一轮 5 道题"在纯鼠标操作下基本走不完。按页签存（与
// Prepare 的 `jobws_prepare_tab` 同族键名）。令牌**不存**：它十分钟过期。
const ROUND_KEY = "jobws_drill_round";

export type DrillRound = {
  items: BankRow[];
  index: number;
  revealed: boolean;
  drawn: boolean;
  graded: number;
  /** 三态计数（抽题时后端给的快照）：结束卡显示"练到哪了"；旧存储没有这字段，读取处兜底 */
  counts: Record<string, number>;
};

/** 读回上一轮（存储被禁用 / 内容不是 JSON 时当作没存过，不影响功能）。 */
export function readDrillRound(): DrillRound | null {
  try {
    const raw = sessionStorage.getItem(ROUND_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as DrillRound;
    return Array.isArray(parsed?.items) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveDrillRound(round: DrillRound): void {
  try {
    sessionStorage.setItem(ROUND_KEY, JSON.stringify(round));
  } catch {
    /* 隐私模式 / 配额满：存不上就退回"刷新即重抽"，不该因此报错打断训练 */
  }
}

export type DrillMode = "due" | "wrong" | "random";

export type DrillResult = {
  items: BankRow[];
  total: number;
  mode: DrillMode;
  /** 三态计数（当前筛选范围内）：结束卡显示"练到哪了"——「会了」在涨（B-4） */
  counts: Record<string, number>;
  filters: { domain: string; subject: string; status: string; keyword: string };
};

export type PreviewToken = {
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

async function requestDrill<T>(path: string): Promise<T> {
  const sep = path.includes("?") ? "&" : "?";
  const qs = currentWorkspace ? `${sep}ws=${encodeURIComponent(currentWorkspace)}` : "";
  const res = await fetch(`/api${path}${qs}`);
  if (!res.ok) throw new Error(humanize(await res.text(), res.status));
  // 工作区自检（与 api.ts 的 issue #22 修复同口径）：后端回显本次实际服务的工作区，
  // 与所选不一致就报错——静默把**别的工作区**的题当成你的题，比报错严重得多。
  const served = res.headers.get("X-Jobws-Workspace");
  if (currentWorkspace && served && served !== currentWorkspace) {
    throw new Error(
      i18n.t("api.workspaceMismatch", { requested: currentWorkspace, served })
    );
  }
  return (await res.json()) as T;
}

/** 抽一轮题（只读）。筛选由后端做，与列表页 / CLI 同一口径。 */
export function fetchDrill(params: {
  mode: DrillMode;
  n: number;
  domain?: string;
  subject?: string;
  keyword?: string;
}): Promise<DrillResult> {
  const q = new URLSearchParams({ mode: params.mode, n: String(params.n) });
  if (params.domain?.trim()) q.set("domain", params.domain.trim());
  if (params.subject?.trim()) q.set("subject", params.subject.trim());
  if (params.keyword?.trim()) q.set("q", params.keyword.trim());
  return requestDrill<DrillResult>(`/progress/questions/drill?${q.toString()}`);
}

/** 标 / 取消标错题的预览（领域层重算标签 → 令牌；落盘走 applyApproval）。 */
export function previewMarkWrong(id: string, on: boolean): Promise<PreviewToken> {
  const q = new URLSearchParams({ id, on: on ? "1" : "0" });
  return requestDrill<PreviewToken>(
    `/progress/questions/preview-wrong?${q.toString()}`
  );
}
