// H-2a 批：类型 / 枚举区整体外移 `lib/domainTypes.ts`（86 个声明、约 740 行）——
// 本文件只留 api 客户端、resumeOptQuery 与工作区状态再导出，水位继续只降不升。
// 声明区经 `export *` 原样再导出，既有 `import { Application } from "../api"` 零改动；
// 新代码请直接从 `lib/domainTypes` 引入类型（此后新增类型不再撑 api.ts 的水位）。
import { currentWorkspace, requestJson as request, setWorkspace } from "./lib/http";
import type {
  Application, ApprovalApplyResult, BackupResult, BankImportPreview, BankListResult,
  Contact, DashboardData, GapResult, HistoryEntry, ImapConfig, ImapFetchResult,
  ImapTestResult, ImportCommitResult, ImportPreviewResult, ImportResult, Interview,
  JobDetail, JobOrder, JobSort, JobStatus, JobSummary, LibraryList, LineageItem, Mail,
  Offer, PrepContent, PrepList, PrepSearch, PrepTogglePreview, ProviderConfig,
  ProviderTestResult, QuestionGroup, ResumeBuildResult, ResumeLayouts,
  ResumeRenderOpts, ResumeTemplateItem, ResumeVersion, SchemaCheckResult,
  StatusSuggestResult, SuggestResult, SystemPaths, Talk, WorkspaceApplyResult,
  WorkspaceItem, WorkspacePreviewResult,
} from "./lib/domainTypes";

// 类型 / 枚举的再导出出口（H-2a 前的旧 import 路径继续可用）。
export * from "./lib/domainTypes";

/** 渲染参数的查询串（空 opts 返回空串——保持 URL 与既有形态一致）。 */
function resumeOptQuery(opts?: ResumeRenderOpts): string {
  const q = new URLSearchParams();
  if (opts?.template) q.set("template", opts.template);
  if (opts?.accent) q.set("accent", opts.accent);
  const s = q.toString();
  return s ? `?${s}` : "";
}

// 全局工作区状态与 HTTP 请求封装已迁 `lib/http.ts`（H-1：api.ts / lib/bank.ts /
// lib/drill.ts / lib/records.ts 四处副本合一）。这里再导出，既有 import 方零改动。
export { currentWorkspace, setWorkspace };

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

  // 链接推断（v0.4.0-A）：本地纯函数，只读（补 scheme、尽力识别来源）
  inferUrl: (url: string) =>
    request<{ ok: boolean; 链接: string; 来源: string; 说明: string[] }>(
      "/applications/infer-url",
      { method: "POST", body: { url } }
    ),

  // CSV 批量导入（第一批）：两阶段。preview 返回差异表不动数据；commit 才写入
  importApplications: (
    csv: string,
    mode: "preview" | "commit" = "preview"
  ) =>
    request<ImportPreviewResult | ImportCommitResult>("/applications/import", {
      method: "POST",
      body: { csv, mode },
    }),

  // --- 工作区：新建同样是两段式（预览拿令牌 → apply 落盘）---
  // 与命令行共用同一份实现：`/preview` 只算清单并登记一次性令牌（不落盘），
  // `/apply` 才真正创建。前端负责把 diff 展示给用户、拿到确认再往下走。
  listDomains: () =>
    request<{ items: { id: string; isDemoDefault: boolean }[]; demoDefault: string }>(
      "/workspaces/domains"
    ),

  previewWorkspace: (body: {
    name: string;
    domain?: string;
    demo?: boolean;
    force?: boolean;
  }) =>
    request<WorkspacePreviewResult>("/workspaces/preview", { method: "POST", body }),

  applyWorkspace: (token: string) =>
    request<WorkspaceApplyResult>("/workspaces/apply", {
      method: "POST",
      body: { token },
    }),

  // 确认令牌的统一落盘入口（两段式的第二步）：令牌一次性、10 分钟有效期、
  // 绑定工作区与载荷指纹。「要写什么」在令牌里、不在请求里。
  // 冲突（预览后数据变了）409、令牌不可用（过期/重放/被改）422。
  applyApproval: (token: string) =>
    request<ApprovalApplyResult>("/approvals/apply", {
      method: "POST",
      body: { token },
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

  // 列表参数与 applications 同一范式：非默认值才传，白名单外的键由后端静默回退。
  // q 为关键词（FC-8）：空串与纯空白一律不传，交给后端当"不筛选"。
  listJobs: (params?: { sort?: JobSort; order?: JobOrder; status?: JobStatus; q?: string }) => {
    const q = new URLSearchParams();
    if (params?.sort && params.sort !== "dir") q.set("sort", params.sort);
    if (params?.order) q.set("order", params.order);
    if (params?.status) q.set("status", params.status);
    if (params?.q?.trim()) q.set("q", params.q.trim());
    const qs = q.toString();
    return request<{ items: JobSummary[]; total: number }>(`/jobs${qs ? `?${qs}` : ""}`);
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

  // 我的题库（questions.csv）：筛选参数交给后端，前端不拉全量再过滤
  bankQuestions: (params?: { domain?: string; subject?: string; status?: string; q?: string }) => {
    const q = new URLSearchParams();
    if (params?.domain) q.set("domain", params.domain);
    if (params?.subject) q.set("subject", params.subject);
    if (params?.status) q.set("status", params.status);
    if (params?.q) q.set("q", params.q);
    const qs = q.toString();
    return request<BankListResult>(`/progress/questions${qs ? `?${qs}` : ""}`);
  },

  // 从 03_面试准备/**/*.md 导入的预览（只读解析；落盘走 applyApproval）
  previewQuestionImport: () =>
    request<BankImportPreview>("/progress/questions/preview-import"),

  // 改题的预览（previewQuestionUpdate）2026-09-21 迁到 lib/bank.ts：那里是题库的
  // 窄模块（B-1/B-2 起），本文件是登记过水位的存量文件（只许变小）。

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

  // 宣讲会 / 招聘会（v0.4.0-A）
  listTalks: (app?: string) =>
    request<{ rows: Talk[]; total: number }>(
      `/progress/talks${app ? `?app=${encodeURIComponent(app)}` : ""}`
    ),

  createTalk: (body: Partial<Talk>) =>
    request<Talk>("/progress/talks", { method: "POST", body }),

  // 邮件（批 4.5）：列表随行带 _openLink（链接构造在后端单一处，前端不做第二份编码）
  listMails: (app?: string) =>
    request<{ rows: Mail[]; total: number }>(
      `/progress/mails${app ? `?app=${encodeURIComponent(app)}` : ""}`
    ),

  createMail: (body: Partial<Mail>) =>
    request<Mail>("/progress/mails", { method: "POST", body }),

  updateMail: (id: string, body: Partial<Mail>) =>
    request<Mail & { _changed?: string[] }>(
      `/progress/mails/${encodeURIComponent(id)}`,
      { method: "PATCH", body }
    ),

  updateTalk: (id: string, body: Partial<Talk>) =>
    request<Talk & { _changed?: string[] }>(
      `/progress/talks/${encodeURIComponent(id)}`,
      { method: "PATCH", body }
    ),

  talksIcsUrl: () => {
    const base = "/api/progress/talks.ics";
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
    request<{ rel: string; type: string; content: string; truncated?: boolean; bytes?: number }>(
      `/library/${section}/content?rel=${encodeURIComponent(rel)}`
    ),

  libraryFileUrl: (section: "facts", rel: string) => {
    const base = `/api/library/${section}/file?rel=${encodeURIComponent(rel)}`;
    return currentWorkspace
      ? `${base}&ws=${encodeURIComponent(currentWorkspace)}`
      : base;
  },

  // 笔记（只读）：03_面试准备 / 04_知识库 的列表与内容（写通道在 approvals，不在本模块）
  prepList: (section: "interview" | "knowledge") =>
    request<PrepList>(`/prep/${section}`),

  prepContent: (section: "interview" | "knowledge", rel: string) =>
    request<PrepContent>(`/prep/${section}/content?rel=${encodeURIComponent(rel)}`),

  // 笔记全文搜索：文件名 + 正文，跨两目录一次返回（只读）
  prepSearch: (q: string) => request<PrepSearch>(`/prep/search?q=${encodeURIComponent(q)}`),

  // 笔记勾选写回：预览（签发令牌）→ 确认后走既有 applyApproval 落盘
  // C-1：一次可翻多行（逗号分隔）；单行 = 长度 1 的列表（批量是唯一路径）
  previewPrepToggle: (
    section: "interview" | "knowledge",
    rel: string,
    lines: number[]
  ) =>
    request<PrepTogglePreview>(
      `/prep/${section}/preview-toggle?rel=${encodeURIComponent(rel)}&lines=${lines.join(",")}`
    ),

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

  // 版式与风格清单（批 4.5）：与 CLI 同一真源（后端 resume_build 常量）
  resumeLayouts: () => request<ResumeLayouts>("/resume/layouts"),

  resumeHtml: (version: string, opts?: ResumeRenderOpts) =>
    request<{ version: string; html: string }>(
      `/resume/${encodeURIComponent(version)}/html${resumeOptQuery(opts)}`
    ),

  buildResume: (version: string, opts?: ResumeRenderOpts) =>
    request<ResumeBuildResult>(
      `/resume/${encodeURIComponent(version)}/build${resumeOptQuery(opts)}`,
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
  resumeDocUrl: (version: string, opts?: ResumeRenderOpts) => {
    const q = resumeOptQuery(opts);
    const base = `/api/resume/${encodeURIComponent(version)}/doc${q}`;
    return currentWorkspace
      ? `${base}${q ? "&" : "?"}ws=${encodeURIComponent(currentWorkspace)}`
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

  openFolder: (which: "workspace" | "snapshots" | "dataRoot") =>
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

  fetchImapMessages: (body: { limit?: number; folder?: string; since_days?: number }) =>
    request<ImapFetchResult>("/imap/fetch", { method: "POST", body }),
};

