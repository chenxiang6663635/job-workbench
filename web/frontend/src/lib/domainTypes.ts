// 领域类型与枚举的唯一声明区（H-2a 批自 api.ts 整体外移，内容原样未改）。
// 只放纯声明（interface / type / 常量枚举）；运行时逻辑不进这里。
// 各枚举与后端真值源的对应关系见条目上方注释（如 STAGES ↔ tools/tracker.py）。

export interface StaleItem {
  id: string;
  公司: string;
  岗位: string;
  当前阶段: string;
  days: number;
  since: string;
  说明: string;
}

// 健康度理由的结构化形态（与 reasons 按下标一一对应）：CLI 与中文界面继续
// 显示 reasons 原文，英文界面按 code 在前端拼句；params 是原始数据（阶段是
// 枚举原值、动作是用户原文），翻译由显示层负责
export interface ReasonHint {
  code: string;
  params: Record<string, string | number>;
}

// 待推进（第二批）：健康度非 ok 且非终态的记录，与追踪表 health 排序同源
export interface PendingItem {
  id: string;
  公司: string;
  岗位: string;
  当前阶段: string;
  level: "urgent" | "overdue" | "stale";
  reasons: string[];
  hints?: ReasonHint[];
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

// 看板「近 7 天宣讲会」的一条：数据来自 talks.csv（与主表时间线无关）
export interface UpcomingTalkItem {
  id: string;
  公司: string;
  /** 原始「时间」列（YYYY-MM-DD HH:MM，可能只有日期） */
  时间: string;
  形式: string;
  地点或链接: string;
  是否参加: string;
  /** 纯日期窗口判定用（后端给） */
  date: string;
}

export interface DashboardData {
  total: number;
  active: number;
  // 列表只给前几条，总数单独给：岗位池大起来时返回体不该跟着膨胀
  unappliedHigh: UnappliedHighItem[];
  unappliedHighTotal: number;
  scoreByState: ScoreStateBucket[];
  /** 最近动作（时间线最近 12 条，附公司名）——看板活动流 */
  recentActivity: {
    time: string;
    id: string;
    company: string;
    field: string;
    old: string;
    new: string;
  }[];
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
  /** 近 7 天宣讲会（2026-09-18）：投递前的日程，与主表时间线无关 */
  upcomingTalks: UpcomingTalkItem[];
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

// 失败原因聚类（第三批）：样本不足时 shown=false，note 说明"样本太少，暂不展示"；
// noteCode/noteParams 是 note 的结构化形态（英文界面按 code 拼句）
export interface FailureClusters {
  shown: boolean;
  note: string;
  noteCode?: string | null;
  noteParams?: Record<string, string | number>;
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
  /** 岗位页原始链接（可从「新增投递」表单或 CLI --link 写入，可空） */
  链接: string;
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
  // 健康度（第二批）：level 为 null 表示终态不参与判定；reasons 给人看，
  // hints 是逐条对应的结构化形态（英文界面按 code 拼句）
  health?: {
    level: "urgent" | "overdue" | "stale" | "ok" | null;
    reasons: string[];
    hints?: ReasonHint[];
  };
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

// CSV 批量导入：preview 结果（新增/重复/错误分色展示，不动数据）。
// `token` 是**可提交时**（无错误行且有将新增行）发出的一次性确认令牌：确认后
// 拿它调 applyApproval 落盘——与 CLI/MCP 共用同一套两段式协议。
export interface ImportPreviewResult {
  mode: "preview";
  unknown: string[];
  counts: { ok: number; duplicate: number; error: number };
  ok: ImportRowIssue[];
  duplicate: ImportRowIssue[];
  error: ImportRowIssue[];
  token: string | null;
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

// 我的题库 `questions.csv` 的一行。字段名是**工作区里的真实列名**（与 CSV 表头、
// CLI、后端、`track check` 四处同一个字面量）——按 i18n 的「四类不翻」约定不翻译：
// 翻了就等于给数据改名，四处会静默失配。
export interface BankQuestion {
  题目id: string;
  题目: string;
  领域: string;
  科目: string;
  标签: string;
  难度: string;
  答案要点: string;
  来源: string;
  关联公司: string;
  关联岗位: string;
  状态: string;
  创建日期: string;
  最近复习: string;
  备注: string;
}

export interface BankListResult {
  items: BankQuestion[];
  total: number;
  counts: Record<string, number>;
  filters: { domain: string; subject: string; status: string; keyword: string };
}

// 1a 导入的预览结果：只有令牌与差异表，**没有**落盘——写通道统一走 applyApproval
export interface BankImportPreview {
  token: string;
  summary: string;
  diff: string[];
  expiresAt: number;
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

// 笔记勾选写回：预览返回形状与题库预览一致（token + 摘要 + 差异 + 过期时刻）
export type PrepTogglePreview = BankImportPreview;

// 笔记全文搜索：一条命中 = 一行（section/rel 足以打开，line 足以定位）
export interface PrepSearchHit {
  section: "interview" | "knowledge";
  rel: string;
  name: string;
  line: number;
  text: string;
  inName: boolean;
}

export interface PrepSearch {
  keyword: string;
  items: PrepSearchHit[];
  /** 真实命中总数（不是返回条数——截断时两者不同，UI 据此说清"另有 N 条"） */
  total: number;
  truncated: boolean;
  skipped: { rel: string; reason: string }[];
}

// 笔记（只读）：03_面试准备 / 04_知识库 —— 字段与工作区真实文件一一对应
export interface PrepFile {
  rel: string;
  name: string;
  size: number;
  mtime: number;
}

export interface PrepList {
  section: string;
  items: PrepFile[];
  total: number;
}

export interface PrepContent {
  rel: string;
  content: string;
  truncated: boolean;
  bytes: number;
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

/** 版式与风格的渲染参数（批 4.5）：预览 / 生成 / Word 三处共用同一组参数名。 */
export interface ResumeRenderOpts {
  template?: string;
  accent?: string;
}

/** 「版式 + 风格」清单（GET /api/resume/layouts）：与 CLI 同一真源。 */
export interface ResumeLayouts {
  /** 可用版式 id（templates/ 目录下的文件名） */
  templates: string[];
  /** 默认版式 id */
  default: string;
  /** 风格预设：中文名 → #hex（预设名保留原名不翻译） */
  accents: Record<string, string>;
  /** 工作区偏好 resume_style（可能为空串） */
  preferredAccent: string;
}

// 高级模板（手写 HTML 精排版）的文件条目，与 LibraryItem 同构但归简历域
export interface SystemPaths {
  workspace: string;
  dataRoot: string;
  mode: "portable" | "user";
  snapshotDir: string;
  snapshotCount: number;
  lastBackup: string | null;
  /** 应用版本（机器形态 YY.M.D，如 26.9.15）；未注入且读不到时为 ""（界面显示「未知」） */
  appVersion: string;
  /** 运行平台（sys.platform：win32 / darwin / linux） */
  platform: string;
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
  /** 会议/作答链接（在线面试的入会地址、笔试作答页等，可空） */
  链接: string;
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

// 宣讲会 / 招聘会（v0.4.0-A）：独立表 talks.csv，与投递记录用「关联记录」相连。
export interface Talk {
  宣讲会id: string;
  公司: string;
  时间: string;
  形式: string;
  地点或链接: string;
  关联记录: string;
  是否参加: string;
  收获: string;
  备注: string;
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

// 顺序与 tools/tracker.py 的 STAGES + TERMINAL_STAGES 逐一对应（阶段流转顺序）。
// 这里的每个值都会出现在筛选与行内下拉里；新增值必须同批更新 tracker.py——
// 后端落盘校验只认那份真值源，两处漂移会出现「下拉能选、保存被拒」。
export const STAGES = [
  "待投",
  "已投",
  "测评",
  "笔试",
  "AI面",
  "群面",
  "一面",
  "二面",
  "三面",
  "HR面",
  "终面",
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
  /** RFC822 Message-ID 规范值（批 4.5，去 `<>`）——记入邮件台账与 Gmail 深链用 */
  messageId?: string;
  /** text/calendar 部件原文（批 9）：会议邀请的结构化真相源；无则为空串 */
  calendar?: string;
}

/** 一条候选事实（批 9）：领域层 `mail_facts.extract_facts` 的输出，前端只消费不改写。 */
export interface MailFact {
  /** 时间 / 会议链接 / 阶段 / 公司岗位 */
  kind: "时间" | "会议链接" | "阶段" | "公司岗位";
  /** 规范化取值（ISO 日期时间 / 规范化链接 / 阶段名 / 记录 id） */
  value: string;
  /** 面向用户的短标题（界面按 kind 出本地化标题，label 作兜底） */
  label: string;
  /** 命中的原文片段（可追溯） */
  evidence: string;
  /** 把握程度：low 的值需用户核对后才可写入 */
  confidence: "high" | "low";
  source: "ics" | "body" | "ai";
  /** 命中的投递记录 id；未命中为空串 */
  targetId: string;
  /** 补充说明（重复会议、缺年份等；可为空） */
  note: string;
}

export interface MailFactsResult {
  facts: MailFact[];
  total: number;
}

export interface ImapFetchResult {
  messages: ImapMessage[];
  count: number;
  server: string;
  folder: string;
  /** 实际生效的时间窗（天）；0 = 不限 */
  sinceDays: number;
  /** 恒为 true：拉取只做取样，不改动任何数据 */
  dryRun: boolean;
  note: string;
}

export const BATCHES = ["提前批", "正式批", "补录"];
// 来源枚举：校验只认后端 tracker.SOURCES 那一份，这里是展示用的同步副本——
// 新增来源必须同批改 tracker.py，否则会出现「下拉能选、保存被拒」。
export const SOURCES = ["应届生求职网", "牛客", "企业校招官网", "学校就业网", "内推",
  "宣讲会", "招聘会", "其他"];
// 方向 ID 取决于工作区装入的领域插件（后端 available_directions 动态读
// <工作区>/config/directions/*.md）。此处是前端可选项的默认清单，与 Applications 页共用一份，
// 避免两页各写一份后漂移；后端在插件不可用时对未知方向放行。
export const DIRECTIONS = ["datacenter", "hvac", "other"];

// 面试记录枚举，与后端 tracker.INTERVIEW_* 一致（单一事实源在 tools/jobws.py track）
export const INTERVIEW_ROUNDS = ["测评", "笔试", "AI面", "群面", "一面", "二面",
  "三面", "HR面", "终面", "其他"];
export const INTERVIEW_FORMS = ["现场", "视频", "电话", "其他"];
export const INTERVIEW_RESULTS = ["待定", "通过", "未通过", "取消"];

// 宣讲会 / 招聘会枚举，与后端 tracker.TALK_* 一致（单一事实源在 tools/tracker.py）
export const TALK_FORMS = ["线上", "线下", "其他"];
export const TALK_ATTEND = ["待定", "参加", "不参加"];

// 邮件（批 4.5）：独立表 mails.csv。「_openLink」是后端随行附加的计算字段：
// custom = 用户自粘链接（Outlook 等）/ gmail = 由 Message-ID 构造 / none = 诚实降级。
export interface MailOpenLink {
  kind: "custom" | "gmail" | "none";
  url: string | null;
}

export interface Mail {
  邮件id: string;
  消息id: string;
  关联记录: string;
  方向: string;
  主题: string;
  发件人: string;
  日期: string;
  webmail链接: string;
  标签: string;
  _openLink?: MailOpenLink;
}

// 邮件枚举，与后端 tracker.MAIL_* 一致（单一事实源在 tools/tracker.py）
export const MAIL_DIRECTIONS = ["收", "发"];
export const MAIL_TAGS = ["通知", "邀约", "笔试", "面试", "拒信", "其他"];

/** 新建工作区的预览结果（两段式的第一步：不落盘，只登记一次性令牌）。 */
export type WorkspacePreviewResult = {
  token: string;
  summary: string;
  diff: string[];
  path: string;
  expiresAt: number;
};

/** 凭令牌创建后的结果。 */
export type WorkspaceApplyResult = {
  created: number;
  summary: string;
  path: string;
};

/** 凭确认令牌落盘的结果（/api/approvals/apply：与 CLI/MCP 同一套两段式）。 */
export type ApprovalApplyResult = {
  ok: boolean;
  operation: string;
  summary: string;
  written?: number;
};
