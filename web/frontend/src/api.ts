export interface DashboardData {
  total: number;
  active: number;
  funnel: { stage: string; count: number }[];
  byDirection: { key: string; count: number }[];
  byBatch: { key: string; count: number }[];
  upcoming: {
    id: string;
    公司: string;
    岗位: string;
    date: string;
    reason: string;
    说明: string;
  }[];
  overdue: { id: string; 公司: string; 岗位: string; 截止日期: string }[];
}

export interface Application {
  id: string;
  公司: string;
  岗位: string;
  方向: string;
  批次: string;
  来源: string;
  截止日期: string;
  投递日期: string;
  当前阶段: string;
  下次动作: string;
  下次动作日期: string;
  简历版本: string;
  评分: string;
  归档目录: string;
  备注: string;
}

export interface JobSummary {
  dir: string;
  hasJD: boolean;
  hasCard: boolean;
  score: number | null;
  level: string | null;
  mtime: number | null;
}

export type GateConclusion = "通过" | "不通过" | "待确认" | null;
export type EvidenceLevel = "精确" | "模糊" | "语义" | null;
export type DictLevel = "Primary" | "Secondary" | "Weak" | null;

export interface HardGates {
  items: { key: string; value: string }[];
  conclusion: GateConclusion;
  reason: string | null;
  details: string[];
}

export interface DimHit {
  level: DictLevel;
  label: string;
  evidence: EvidenceLevel;
  note: string | null;
}

export interface DimensionDetail {
  hits: DimHit[];
  raw: string[];
}

export interface JobDetail {
  dir: string;
  jd: string | null;
  cardRaw: string | null;
  card: {
    dimensions: { name: string; score: number; max: number }[];
    total: number | null;
    level: string | null;
    action: string | null;
    consistent: boolean;
    hardGates: HardGates;
    dimensionsDetail: Record<string, DimensionDetail>;
  } | null;
}

export interface LibraryItem {
  rel: string;
  name: string;
  size: number;
  mtime: number;
  kind: "text" | "binary";
}

export interface LibraryList {
  section: string;
  items: LibraryItem[];
  total: number;
}

export interface WorkspaceItem {
  name: string;
  isDefault: boolean;
}

export interface ProviderConfig {
  base_url: string;
  api_key: string;
  hasKey: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  status: number;
  modelCount: number;
  models: string[];
}

export const STAGES = [
  "待投",
  "已投",
  "笔试",
  "一面",
  "二面",
  "三面",
  "HR面",
  "offer",
  "签约",
  "已挂",
  "已放弃",
];

export const BATCHES = ["提前批", "正式批", "补录"];

// 全局当前工作区（相对仓库根，如 personal）。空 = 用后端默认。
export let currentWorkspace = "";
export function setWorkspace(ws: string) {
  currentWorkspace = ws;
}

// 统一在工作区激活时给路径附加 ?ws=。库中 API 在 Web 场景必须显式传 workspace
// （tools/ 模块级 WORKSPACE 全局在并发下会互相覆盖），因此所有请求都带 ws。
async function request<T>(
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
    const detail = await res.text();
    throw new Error(detail || `请求失败 ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<DashboardData>("/dashboard"),

  listApplications: (params: {
    stage?: string;
    direction?: string;
    batch?: string;
  }) => {
    const q = new URLSearchParams();
    if (params.stage) q.set("stage", params.stage);
    if (params.direction) q.set("direction", params.direction);
    if (params.batch) q.set("batch", params.batch);
    const qs = q.toString();
    return request<{ items: Application[]; total: number }>(
      `/applications${qs ? `?${qs}` : ""}`
    );
  },

  addApplication: (body: Partial<Application>) =>
    request<{ id: string; item: Application }>("/applications", {
      method: "POST",
      body,
    }),

  updateApplication: (id: string, body: Partial<Application>) =>
    request<{ item: Application }>(`/applications/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body,
    }),

  listJobs: () => request<{ items: JobSummary[]; total: number }>("/jobs"),

  createJob: (body: { 公司: string; 岗位: string; JD文本: string }) =>
    request<JobSummary>("/jobs", { method: "POST", body }),

  jobDetail: (dir: string) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(dir)}`),

  libraryList: (section: "facts" | "resumes") =>
    request<LibraryList>(`/library/${section}`),

  libraryContent: (section: "facts" | "resumes", rel: string) =>
    request<{ rel: string; type: string; content: string }>(
      `/library/${section}/content?rel=${encodeURIComponent(rel)}`
    ),

  libraryFileUrl: (section: "facts" | "resumes", rel: string) => {
    const base = `/api/library/${section}/file?rel=${encodeURIComponent(rel)}`;
    return currentWorkspace
      ? `${base}&ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  listWorkspaces: () =>
    request<{ items: WorkspaceItem[]; total: number }>("/workspaces"),

  getProvider: () => request<ProviderConfig>("/provider"),

  saveProvider: (body: { base_url: string; api_key: string }) =>
    request<ProviderConfig>("/provider", { method: "POST", body }),

  testProvider: () => request<ProviderTestResult>("/provider/test", {
    method: "POST",
  }),
};
