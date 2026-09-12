export interface StaleItem {
  id: string;
  公司: string;
  岗位: string;
  当前阶段: string;
  days: number;
  since: string;
  说明: string;
}

// 待推进（第二批）：健康度非 ok 且非终态的记录，与追踪表 health 排序同源
export interface PendingItem {
  id: string;
  公司: string;
  岗位: string;
  当前阶段: string;
  level: "urgent" | "overdue" | "stale";
  reasons: string[];
}

// 看板「高分未投」条目（B3）：评分达到「建议投」档下界且追踪表里还没有记录
export interface UnappliedHighItem {
  dir: string;
  company: string;
  role: string;
  score: number;
  level: string | null;
}

// 评分档位 × 投递状态分布（B3）：档位边界由后端 jd_score.THRESHOLDS 派生
export interface ScoreStateBucket {
  tier: string;
  unapplied: number;
  active: number;
  terminal: number;
}

export interface DashboardData {
  total: number;
  active: number;
  // 列表只给前几条，总数单独给：岗位池大起来时返回体不该跟着膨胀
  unappliedHigh: UnappliedHighItem[];
  unappliedHighTotal: number;
  scoreByState: ScoreStateBucket[];
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
  stale: StaleItem[];
  pending: PendingItem[];
  staleDays: number;
  retrospective: Retrospective;
}

// 周期复盘（P3）：转化率由时间线重建「到达过」而非当前存量
export interface FailureCluster {
  category: string;
  count: number;
  examples: string[];
}

// 失败原因聚类（第三批）：样本不足时 shown=false，note 说明"样本太少，暂不展示"
export interface FailureClusters {
  shown: boolean;
  note: string;
  clusters: FailureCluster[];
  total: number;
  minSamples: number;
  source: "keywords" | "reason" | "none";
}

export interface Retrospective {
  total: number;
  conversion: { stage: string; reached: number; advanced: number; rate: number | null }[];
  stay: { stage: string; n: number; median: number; avg: number }[];
  failure: { reason: string; count: number }[];
  declined: { reason: string; count: number }[];
  failureClusters: FailureClusters;
}

export interface SchemaCheckResult {
  ok: boolean;
  version: number;
  versionNote: string | null;
  files: { file: string; ok: boolean; issues: string[]; note: string }[];
  quarantined: { file: string; error: string; moved_to: string }[];
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
  状态原因: string;
  下次动作: string;
  下次动作日期: string;
  简历版本: string;
  评分: string;
  归档目录: string;
  备注: string;
  // 当前阶段已停留天数；无基准日时后端返回空串
  stageDays?: number | "";
  // 健康度（第二批）：level 为 null 表示终态不参与判定；reasons 给人看
  health?: { level: "urgent" | "overdue" | "stale" | "ok" | null; reasons: string[] };
}

export interface HistoryEntry {
  时间: string;
  id: string;
  字段: string;
  原值: string;
  新值: string;
}

// CSV 批量导入（第一批）：preview 的差异表条目
export interface ImportRowIssue {
  line: number;
  row: Record<string, string>;
  errors: string[];
}

// CSV 批量导入：preview 结果（新增/重复/错误分色展示，不动数据）
export interface ImportPreviewResult {
  mode: "preview";
  unknown: string[];
  counts: { ok: number; duplicate: number; error: number };
  ok: ImportRowIssue[];
  duplicate: ImportRowIssue[];
  error: ImportRowIssue[];
}

// CSV 批量导入：commit 结果
export interface ImportCommitResult {
  mode: "commit";
  written: number;
  skipped: number;
}

// 状态建议（B11）：规则层只出建议，改不改由用户逐条确认
export interface StatusSignal {
  kind: string; // reject | offer | interview | test | applied
  stage: string; // 建议阶段
  evidence: string[]; // 命中的原文句子——用户靠它复核判断
}

export interface StatusMatch {
  id: string;
  公司: string;
  岗位: string;
  当前阶段: string;
  建议阶段: string; // 空 = 没识别出线索，需人工选
  可覆盖: boolean;
  原因: string;
  命中: string; // 公司 / 公司+岗位 / 手动指定
  证据: string[];
}

export interface StatusSuggestResult {
  signals: StatusSignal[];
  dates: string[];
  matches: StatusMatch[];
  ambiguous: boolean; // 原文自相矛盾（拒信 + offer 并存）
  unmatched: boolean;
  ambiguous_match: boolean; // 匹配到多条，需用户选
  notes: string[];
}

// 面试题库（第二批）：按公司+岗位归集被问过的问题（只读聚合，无新数据文件）
export interface QuestionItem {
  id: string;
  轮次: string;
  面试时间: string;
  面试官: string;
  结果: string;
  问题记录: string;
  我的回答要点: string;
  复盘与改进: string;
}

export interface QuestionGroup {
  公司: string;
  岗位: string;
  items: QuestionItem[];
  total: number;
}

// 岗位池 ↔ 投递追踪联动（后端 B1 / 前端 B2）
// company / role **只用于展示**（解析卡「基本信息」优先，读不到回退目录名拆分）。
// 关联匹配键一律是目录名——解析卡里填的常是给人看的详细描述，当键会与追踪表系统性失配。
export type ApplyState = "未投递" | "流程中" | "已终态";
// 四排序与状态筛选：取值与后端 jobs.py 的 JOB_SORTS / JOB_STATUS 白名单一致
export type JobSort = "dir" | "score" | "state" | "recent";
// 岗位池排序方向。每个维度的自然默认在后端 JOB_DEFAULT_ORDER（单一真值源）
export type JobOrder = "asc" | "desc";
export type JobStatus = "" | "unapplied" | "active" | "terminal";

export interface JobSummary {
  dir: string;
  hasJD: boolean;
  hasCard: boolean;
  score: number | null;
  level: string | null;
  mtime: number | null;
  company: string;
  role: string;
  applyState: ApplyState;
  stage: string | null;
  applicationId: string | null;
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

export interface ResumeVersion {
  version: string;
  size: number;
  mtime: number;
  hasPdf: boolean;
}

export interface ResumeCheck {
  label: string;
  value: string;
  ok: boolean | null;
}

export interface ResumeBuildResult {
  version: string;
  pdf: string;
  size: number;
  a4: { ok: boolean; message: string };
  checks: ResumeCheck[];
  passed: boolean;
}

// 高级模板（手写 HTML 精排版）的文件条目，与 LibraryItem 同构但归简历域
export interface SystemPaths {
  workspace: string;
  snapshotDir: string;
  snapshotCount: number;
  lastBackup: string | null;
  telemetry: boolean;
  note: string;
}

export interface BackupResult {
  ok: boolean;
  path: string;
  files: number;
  size: number;
  kept: number;
  removed: number;
  snapshotDir: string;
}

export interface ResumeTemplateItem {
  rel: string;
  name: string;
  size: number;
  mtime: number;
  kind: "text" | "binary";
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

export interface Interview {
  面试id: string;
  关联记录: string;
  公司: string;
  岗位: string;
  轮次: string;
  面试时间: string;
  形式: string;
  面试官: string;
  问题记录: string;
  我的回答要点: string;
  复盘与改进: string;
  结果: string;
}

export interface GapTerm {
  term: string;
  level: string;
}

export interface GapResult {
  jd: string;
  resume: string;
  lexicon: string | null;
  matched: GapTerm[];
  injectable: string[];
  missing: string[];
  matchedDetail: GapTerm[];
  injectableDetail: GapTerm[];
  missingDetail: GapTerm[];
  counts: { matched: number; injectable: number; missing: number };
  resumeVersion: string;
  warnings: string[];
}

export interface Contact {
  联系人id: string;
  关联记录: string;
  姓名: string;
  角色: string;
  公司: string;
  联系方式: string;
  来源: string;
  最近联系: string;
  下次跟进: string;
  备注: string;
}

export interface Offer {
  offer_id: string;
  关联记录: string;
  公司: string;
  岗位: string;
  薪资构成: string;
  月薪: string;
  年终: string;
  签字费: string;
  股票期权: string;
  工作地点: string;
  答复截止日: string;
  其他条件: string;
  备注: string;
}

export interface LineageItem {
  version: string;
  total: number;
  applications: {
    id: string;
    公司: string;
    岗位: string;
    当前阶段: string;
    投递日期: string;
  }[];
}

export interface SuggestResult {
  version: string;
  ok: boolean;
  issues: string[];
  suggestion: Record<string, unknown>;
  model: string;
}

// 简历一键导入（第一批）：抽取 + BYOK 结构化 + 可溯源校验的结果，绝不落盘
export interface ImportResult {
  file: string;
  characters: number;
  text: string; // 抽取到的原文，供用户逐段核对
  data: Record<string, unknown>; // 结构化简历（与标准版式 schema 同构）
  issues: string[]; // 可溯源校验未过：值/数字对不上原文，标红「疑似模型补全」
  unfilled: string[]; // 模型未抽到的关键字段，标黄提示补填
  model: string;
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
  "我拒绝的 offer",
];

// 终态阶段：进入后「当前阶段」锁定，不可回退；与后端 tracker.TERMINAL_STAGES 一致。
// 「我拒绝的 offer」是双向选择不是失败——复盘归因里单独统计
export const TERMINAL = ["已挂", "已放弃", "我拒绝的 offer"];
// 失败类终态（红色徽章用）；拒绝的 offer 用中性色
export const FAIL_TERMINAL = ["已挂", "已放弃"];

// ---- IMAP 只读拉取（B11）----
// 授权码只存工作区本地 config/imap.json；接口回传的 password 是脱敏展示值。
export interface ImapConfig {
  host: string;
  port: number;
  user: string;
  folder: string;
  password: string;
  hasPassword: boolean;
  /** host 留空时将使用的服务器；未知域名返回空串 */
  serverHint: string;
}

export interface ImapTestResult {
  ok: boolean;
  server: string;
  folder: string;
  messageCount: number;
  note: string;
}

export interface ImapMessage {
  uid: string;
  subject: string;
  from: string;
  date: string;
  body: string;
}

export interface ImapFetchResult {
  messages: ImapMessage[];
  count: number;
  server: string;
  folder: string;
  /** 恒为 true：拉取只做取样，不改动任何数据 */
  dryRun: boolean;
  note: string;
}

export const BATCHES = ["提前批", "正式批", "补录"];
// 方向 ID 取决于工作区装入的领域插件（后端 available_directions 动态读
// <工作区>/config/directions/*.md）。此处是前端可选项的默认清单，与 Applications 页共用一份，
// 避免两页各写一份后漂移；后端在插件不可用时对未知方向放行。
export const DIRECTIONS = ["datacenter", "hvac", "other"];

// 面试记录枚举，与后端 tracker.INTERVIEW_* 一致（单一事实源在 tools/tracker.py）
export const INTERVIEW_ROUNDS = ["笔试", "一面", "二面", "三面", "HR面", "终面", "其他"];
export const INTERVIEW_FORMS = ["现场", "视频", "电话", "其他"];
export const INTERVIEW_RESULTS = ["待定", "通过", "未通过", "取消"];

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
    throw new Error(humanizeError(await res.text(), res.status));
  }
  // 工作区自检（issue #22）：后端会回显本次实际服务的工作区。若与所选不一致就报错，
  // 而不是把别的工作区的数据当成你的数据展示出来——静默错位的后果比报错严重得多。
  // 两端都有值才比较：缺头（旧后端 / 跨源未暴露）时不误报。
  const served = res.headers.get("X-Jobws-Workspace");
  if (currentWorkspace && served && served !== currentWorkspace) {
    throw new Error(
      `工作区不一致：请求的是 ${currentWorkspace}，服务端实际返回 ${served}。已阻止展示，避免张冠李戴。`
    );
  }
  return res.json() as Promise<T>;
}

// 后端错误统一是 {"detail": "..."}；直接把原始 JSON 抛给 UI 会显示一坨花括号
// （端到端验证时就出现过 {"detail":"Method Not Allowed"}），这里抽成人话。
// 校验错误（422）的 detail 是数组，逐条拼接；非 JSON（纯文本 404 等）按原文返回。
function humanizeError(raw: string, status: number): string {
  const fallback = `请求失败 ${status}`;
  if (!raw.trim()) return fallback;
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
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

export const api = {
  dashboard: () => request<DashboardData>("/dashboard"),

  listApplications: (params: {
    stage?: string;
    direction?: string;
    batch?: string;
    q?: string;
    sort?: string;
  }) => {
    const q = new URLSearchParams();
    if (params.stage) q.set("stage", params.stage);
    if (params.direction) q.set("direction", params.direction);
    if (params.batch) q.set("batch", params.batch);
    if (params.q) q.set("q", params.q);
    if (params.sort && params.sort !== "default") q.set("sort", params.sort);
    const qs = q.toString();
    return request<{ items: Application[]; total: number }>(
      `/applications${qs ? `?${qs}` : ""}`
    );
  },

  applicationHistory: (id: string) =>
    request<{ id: string; items: HistoryEntry[]; total: number }>(
      `/applications/${encodeURIComponent(id)}/history`
    ),

  // `岗位目录`（如 `某公司_某岗位`）是「岗位池 → 投递」的推荐入口：给了它，
  // 公司与岗位由后端按同一口径拆分，客户端不必自己拆（拆分只有一处实现）。
  addApplication: (body: Partial<Application> & { 岗位目录?: string }) =>
    request<{ id: string; item: Application }>("/applications", {
      method: "POST",
      body,
    }),

  updateApplication: (id: string, body: Partial<Application>) =>
    request<{ item: Application }>(`/applications/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body,
    }),

  // CSV 批量导入（第一批）：两阶段。preview 返回差异表不动数据；commit 才写入
  importApplications: (
    csv: string,
    mode: "preview" | "commit" = "preview"
  ) =>
    request<ImportPreviewResult | ImportCommitResult>("/applications/import", {
      method: "POST",
      body: { csv, mode },
    }),

  // 原文 → 状态建议（B11）：**只读**，不动追踪表、不写时间线。
  // id 非空 = 用户手动指定记录（站内信常常通篇不写公司名）。
  suggestStatus: (text: string, id?: string) =>
    request<StatusSuggestResult>("/applications/suggest-status", {
      method: "POST",
      // 没指定记录时**整个字段不发**：显式传 null 曾把后端打成 422
      body: id ? { 原文: text, id } : { 原文: text },
    }),

  // 用户确认后写回一条建议。服务端会在锁内重算单调性与并发前提：
  // 409 = 记录在你确认期间变了（要重新解析）；422 = 规则不允许这么改
  applyStatusSuggestion: (body: {
    id: string;
    阶段: string;
    原阶段?: string;
    状态原因?: string;
    下次动作?: string;
    下次动作日期?: string;
    依据?: string;
  }) =>
    request<{ item: Application }>("/applications/apply-status-suggestion", {
      method: "POST",
      body,
    }),

  // 列表参数与 applications 同一范式：非默认值才传，白名单外的键由后端静默回退
  listJobs: (params?: { sort?: JobSort; order?: JobOrder; status?: JobStatus }) => {
    const q = new URLSearchParams();
    if (params?.sort && params.sort !== "dir") q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<{ items: JobSummary[]; total: number }>(
      `/jobs${qs ? `?${qs}` : ""}`
    );
  },

  jobGap: (dir: string, resume?: string) => {
    const q = resume ? `?resume=${encodeURIComponent(resume)}` : "";
    return request<GapResult>(
      `/jobs/${encodeURIComponent(dir)}/gap${q}`
    );
  },

  listInterviews: (params?: { app?: string; result?: string }) => {
    const q = new URLSearchParams();
    if (params?.app) q.set("app", params.app);
    if (params?.result) q.set("result", params.result);
    const qs = q.toString();
    return request<{ rows: Interview[]; total: number }>(
      `/progress/interviews${qs ? `?${qs}` : ""}`
    );
  },

  createInterview: (body: Partial<Interview>) =>
    request<Interview>("/progress/interviews", { method: "POST", body }),

  // 面试题库：按公司+岗位归集已答过的问题，q 为关键词（跨问题/回答/复盘匹配）
  questionBank: (q?: string) =>
    request<{ groups: QuestionGroup[]; total: number; keyword: string }>(
      `/progress/question-bank${q ? `?q=${encodeURIComponent(q)}` : ""}`
    ),

  updateInterview: (id: string, body: Partial<Interview>) =>
    request<Interview & { _changed?: string[] }>(
      `/progress/interviews/${encodeURIComponent(id)}`,
      { method: "PATCH", body }
    ),

  interviewIcsUrl: () => {
    const base = "/api/progress/interviews.ics";
    return currentWorkspace
      ? `${base}?ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  listContacts: (app?: string) =>
    request<{ rows: Contact[]; total: number }>(
      `/progress/contacts${app ? `?app=${encodeURIComponent(app)}` : ""}`
    ),

  createContact: (body: Partial<Contact>) =>
    request<Contact>("/progress/contacts", { method: "POST", body }),

  updateContact: (id: string, body: Partial<Contact>) =>
    request<Contact & { _changed?: string[] }>(
      `/progress/contacts/${encodeURIComponent(id)}`,
      { method: "PATCH", body }
    ),

  listOffers: (app?: string) =>
    request<{ rows: Offer[]; total: number }>(
      `/progress/offers${app ? `?app=${encodeURIComponent(app)}` : ""}`
    ),

  createOffer: (body: Partial<Offer>) =>
    request<Offer>("/progress/offers", { method: "POST", body }),

  updateOffer: (id: string, body: Partial<Offer>) =>
    request<Offer & { _changed?: string[] }>(
      `/progress/offers/${encodeURIComponent(id)}`,
      { method: "PATCH", body }
    ),

  lineage: () =>
    request<{ items: LineageItem[]; total: number }>("/progress/lineage"),

  createJob: (body: { 公司: string; 岗位: string; JD文本: string }) =>
    request<JobSummary>("/jobs", { method: "POST", body }),

  // JD 链接抓取（第三批）：抓取失败或正文过短由后端 502/422 明确降级，前端照抄提示
  fetchJd: (body: { url: string; 公司: string; 岗位: string }) =>
    request<JobSummary & { characters: number; url: string }>("/jobs/fetch-jd", {
      method: "POST",
      body,
    }),

  jobDetail: (dir: string) =>
    request<JobDetail>(`/jobs/${encodeURIComponent(dir)}`),

  libraryList: (section: "facts") =>
    request<LibraryList>(`/library/${section}`),

  libraryContent: (section: "facts", rel: string) =>
    request<{ rel: string; type: string; content: string }>(
      `/library/${section}/content?rel=${encodeURIComponent(rel)}`
    ),

  libraryFileUrl: (section: "facts", rel: string) => {
    const base = `/api/library/${section}/file?rel=${encodeURIComponent(rel)}`;
    return currentWorkspace
      ? `${base}&ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  listWorkspaces: () =>
    request<{ items: WorkspaceItem[]; total: number }>("/workspaces"),

  listResumeVersions: () =>
    request<{ items: ResumeVersion[]; total: number }>("/resume"),

  getResume: (version: string) =>
    request<{ version: string; data: Record<string, unknown> }>(
      `/resume/${encodeURIComponent(version)}`
    ),

  saveResume: (version: string, data: Record<string, unknown>) =>
    request<{ version: string; saved: boolean }>(
      `/resume/${encodeURIComponent(version)}`,
      { method: "PUT", body: { data } }
    ),

  resumeHtml: (version: string) =>
    request<{ version: string; html: string }>(
      `/resume/${encodeURIComponent(version)}/html`
    ),

  buildResume: (version: string) =>
    request<ResumeBuildResult>(
      `/resume/${encodeURIComponent(version)}/build`,
      { method: "POST" }
    ),

  suggestRewrite: (
    version: string,
    body: { instruction: string; model: string }
  ) =>
    request<SuggestResult>(`/resume/${encodeURIComponent(version)}/suggest`, {
      method: "POST",
      body,
    }),

  // 简历一键导入：上传文件（base64）→ 抽取 → 结构化 → 可溯源校验。
  // 本接口只返回核对数据，不落盘；确认后由调用方走 saveResume 保存。
  importResume: (body: { filename: string; content_base64: string; model: string }) =>
    request<ImportResult>("/resume/import", { method: "POST", body }),

  // Word 导出（.doc）：浏览器直接下载，链接需带 ws 与其他 GET 一致
  resumeDocUrl: (version: string) => {
    const base = `/api/resume/${encodeURIComponent(version)}/doc`;
    return currentWorkspace
      ? `${base}?ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  // 高级模板（手写 HTML）：只读浏览与生成，文件能力自素材库迁入
  listResumeTemplates: () =>
    request<{ items: ResumeTemplateItem[]; total: number }>("/resume/templates"),

  resumeTemplateContent: (rel: string) =>
    request<{ rel: string; type: string; content: string }>(
      `/resume/templates/content?rel=${encodeURIComponent(rel)}`
    ),

  resumeTemplateFileUrl: (rel: string) => {
    const base = `/api/resume/templates/file/${rel
      .split("/")
      .map((p) => encodeURIComponent(p))
      .join("/")}`;
    return currentWorkspace
      ? `${base}?ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  systemPaths: () => request<SystemPaths>("/system/paths"),

  systemCheck: () => request<SchemaCheckResult>("/system/check"),

  backupWorkspace: () =>
    request<BackupResult>("/system/backup", { method: "POST" }),

  openFolder: (which: "workspace" | "snapshots") =>
    request<{ ok: boolean; path: string }>("/system/open-folder", {
      method: "POST",
      body: { path: which },
    }),

  exportUrl: () => {
    const base = "/api/system/export";
    return currentWorkspace
      ? `${base}?ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  buildResumeTemplate: (version: string) =>
    request<ResumeBuildResult>(
      `/resume/templates/${encodeURIComponent(version)}/build`,
      { method: "POST" }
    ),

  getProvider: () => request<ProviderConfig>("/provider"),

  saveProvider: (body: { base_url: string; api_key: string }) =>
    request<ProviderConfig>("/provider", { method: "POST", body }),

  testProvider: () => request<ProviderTestResult>("/provider/test", {
    method: "POST",
  }),

  // ---- IMAP 只读拉取（B11）----
  // fetch 是 dry-run：只返回邮件列表供挑选，不动追踪表；
  // 写回仍走 applyStatusSuggestion（逐条确认后才写）。
  getImap: () => request<ImapConfig>("/imap"),

  saveImap: (body: {
    host: string;
    port: number;
    user: string;
    password: string; // 传空 = 保留已保存的值
    folder: string;
  }) => request<ImapConfig>("/imap", { method: "POST", body }),

  testImap: () => request<ImapTestResult>("/imap/test", { method: "POST" }),

  fetchImapMessages: (body: { limit?: number; folder?: string }) =>
    request<ImapFetchResult>("/imap/fetch", { method: "POST", body }),
};
