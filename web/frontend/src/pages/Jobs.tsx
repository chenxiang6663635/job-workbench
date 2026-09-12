import { useEffect, useState } from "react";
import { ChevronsUpDown, Inbox, Link2, Loader2, Plus } from "lucide-react";
import {
  api,
  BATCHES,
  DIRECTIONS,
  STAGES,
  type JobSort,
  type JobStatus,
  type JobSummary,
} from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input, Textarea } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import JobCard from "../components/JobCard";
import JobDetailView from "../components/JobDetailView";

// 四排序与后端 jobs.py 的 JOB_SORTS 白名单一致；未知键由后端静默回退 dir
const SORT_LABELS: Record<JobSort, string> = {
  dir: "目录名",
  score: "评分",
  state: "投递状态",
  recent: "最近更新",
};

const STATUS_ITEMS: { value: JobStatus; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "unapplied", label: "未投递" },
  { value: "active", label: "流程中" },
  { value: "terminal", label: "已终态" },
];

// Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达（与 Applications 同）
const ALL = "__all__";

// 下钻约定：追踪表在 mount 时读它并展开 focusId 对应行（看板已在用同一把钥匙）
const DRILL_KEY = "jobws_drill";

function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** 目录名 → (公司, 岗位)，与后端 `_split_dir` 同一口径：取首个下划线 */
function splitDir(dir: string): [string, string] {
  const i = dir.indexOf("_");
  return i < 0 ? [dir, ""] : [dir.slice(0, i), dir.slice(i + 1)];
}

export default function Jobs() {
  const [items, setItems] = useState<Awaited<ReturnType<typeof api.listJobs>>["items"]>([]);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof api.jobDetail>> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [draft, setDraft] = useState({ 公司: "", 岗位: "", JD文本: "" });
  // JD 链接抓取（第三批）：尽力而为，失败即明确降级提示手动粘贴
  const [jdUrl, setJdUrl] = useState("");
  const [fetching, setFetching] = useState(false);
  const [sort, setSort] = useState<JobSort>("dir");
  const [status, setStatus] = useState<JobStatus>("");
  // 正在投递的岗位目录（按钮级 loading）：写追踪表是写操作，必须给出进行中反馈
  const [applying, setApplying] = useState<string | null>(null);
  // 一键投递的确认目标。「一键」省掉的是重填公司与岗位，不是省掉确认：
  // 方向 / 批次是追踪表必填字段，且创建后不能改（后端 UPDATABLE 不含这两列），
  // 替用户猜一个写进去，就是一条再也改不回来的脏数据。
  const [applyTarget, setApplyTarget] = useState<JobSummary | null>(null);
  const [applyDraft, setApplyDraft] = useState({
    方向: "other",
    批次: "正式批",
    当前阶段: "已投",
    投递日期: today(),
  });

  const load = () => {
    setLoading(true);
    api
      .listJobs({ sort, status })
      .then(
        (r) => setItems(r.items),
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  };

  useEffect(load, [sort, status]);

  // 详情拉取期间补 loading 态：此前点击到返回前无任何骨架，像卡住
  const open = (dir: string) => {
    setDetailLoading(true);
    api
      .jobDetail(dir)
      .then((d) => setDetail(d))
      .catch((e: Error) => setError(e.message))
      .then(() => setDetailLoading(false));
  };

  const closeDetail = () => {
    setDetail(null);
    setExpanded(null);
  };

  // 抓取成功后后端已写入 JD原文.md，直接打开详情让用户核对原文——
  // 抓取只是省掉复制粘贴，内容仍必须由用户过目（不做任何改写或摘要）
  const fetchJd = () => {
    if (!draft.公司.trim() || !draft.岗位.trim()) {
      setError("抓取前先填公司与岗位（决定 JD 存在哪个岗位目录）");
      return;
    }
    setFetching(true);
    setError(null);
    api
      .fetchJd({ url: jdUrl.trim(), 公司: draft.公司.trim(), 岗位: draft.岗位.trim() })
      .then((r) => {
        setFetching(false);
        setCreating(false);
        setJdUrl("");
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
        open(r.dir);
      })
      .catch((e: Error) => {
        setError(e.message);
        setFetching(false);
      });
  };

  const submit = () => {
    api
      .createJob(draft)
      .then(() => {
        setCreating(false);
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  const sortBtn = (key: JobSort) => {
    const active = sort === key;
    return (
      <button
        onClick={() => setSort(active ? "dir" : key)}
        className={`flex cursor-pointer items-center gap-1 font-medium transition-colors ${
          active ? "text-primary" : "text-muted-foreground hover:text-foreground"
        }`}
        title={`按${SORT_LABELS[key]}排序`}
      >
        {SORT_LABELS[key]}
        <ChevronsUpDown size={12} className={active ? "opacity-100" : "opacity-40"} />
      </button>
    );
  };

  const startApply = (job: JobSummary) => {
    const [, role] = splitDir(job.dir);
    if (!role) {
      setError(
        `目录「${job.dir}」里没有下划线，拆不出公司与岗位，请到追踪表手动新增（关联键 = 目录名）`
      );
      return;
    }
    setError(null);
    setApplyTarget(job);
  };

  // 写入追踪表用**目录名拆分值**而非卡片展示名：匹配键是目录名，
  // 写展示名会让这条记录在岗位池里匹配不上（B1 审查抓出的就是这个问题）。
  const submitApply = () => {
    if (!applyTarget) return;
    const [公司, 岗位] = splitDir(applyTarget.dir);
    setApplying(applyTarget.dir);
    setError(null);
    api
      .addApplication({
        公司,
        岗位,
        ...applyDraft,
        评分: String(applyTarget.score ?? 0),
      })
      .then((r) => {
        setApplying(null);
        setApplyTarget(null);
        // 跳追踪表并展开新行：复用看板下钻的既有约定（sessionStorage + hash 路由）
        try {
          sessionStorage.setItem(DRILL_KEY, JSON.stringify({ focusId: r.id }));
        } catch {
          // sessionStorage 不可用时退化为只跳页面，不展开该行
        }
        window.location.hash = "applications";
      })
      .catch((e: Error) => {
        // 409（同公司+岗位已存在）由后端给出可读文案，直接照抄给用户
        setError(e.message);
        setApplying(null);
      });
  };

  if (detail) {
    return (
      <JobDetailView
        detail={detail}
        expanded={expanded}
        onToggleDimension={(name) => setExpanded(expanded === name ? null : name)}
        onBack={closeDetail}
      />
    );
  }

  if (detailLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          共 {items.length} 个岗位
          {status
            ? `（已按「${STATUS_ITEMS.find((s) => s.value === status)?.label}」筛选）`
            : ""}
          ，评分由 AI 完成写入解析卡后展示
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> 新建岗位
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-muted-foreground">排序</span>
          {(Object.keys(SORT_LABELS) as JobSort[]).map((key) => (
            <span key={key} className="inline-flex items-center gap-1">
              {sortBtn(key)}
            </span>
          ))}
        </div>
        <Select
          value={status === "" ? ALL : status}
          onValueChange={(v) => setStatus(v === ALL ? "" : (v as JobStatus))}
        >
          <SelectTrigger className="w-32">
            <SelectValue placeholder="全部状态" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_ITEMS.map((s) => (
              <SelectItem key={s.value || ALL} value={s.value || ALL}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {creating && (
        <Card className="space-y-3 border-primary/30 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              placeholder="公司名称"
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <Input
              placeholder="岗位名称"
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
          </div>
          {/* JD 链接抓取：省掉复制粘贴，但抓不到会直说，不假装成功 */}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="flex-1"
              placeholder="JD 网页链接（选填）：https://… 抓取成功后自动存为 JD原文.md"
              value={jdUrl}
              onChange={(e) => setJdUrl(e.target.value)}
            />
            <Button
              variant="outline"
              onClick={fetchJd}
              disabled={
                fetching || !jdUrl.trim() || !draft.公司.trim() || !draft.岗位.trim()
              }
              title={!draft.公司.trim() || !draft.岗位.trim() ? "先填公司与岗位" : "抓取网页正文"}
            >
              {fetching ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
              {fetching ? "抓取中…" : "从链接抓取"}
            </Button>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground/70">
            只取网页正文，不做改写或摘要。需登录、有反爬或纯 JS 渲染的页面抓不到，
            会明确提示你手动粘贴——不会把半截内容当成抓取成功。
          </p>
          <Textarea
            className="min-h-[12rem] resize-y font-mono text-xs leading-relaxed"
            placeholder="粘贴完整的 JD 原文（含岗位职责与任职要求）。原文会被完整保存，不做改写或摘要。"
            value={draft.JD文本}
            onChange={(e) => setDraft({ ...draft, JD文本: e.target.value })}
          />
          <div className="flex gap-2">
            <Button
              onClick={submit}
              disabled={
                !draft.公司.trim() || !draft.岗位.trim() || !draft.JD文本.trim()
              }
            >
              保存岗位
            </Button>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
          </div>
        </Card>
      )}

      {applyTarget && (
        <Card className="space-y-3 border-primary/30 p-5">
          <p className="text-sm font-medium text-foreground">
            确认投递：{applyTarget.company} · {applyTarget.role}
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            公司与岗位取自目录名{" "}
            <code className="rounded bg-background px-1 py-0.5 text-foreground">
              {applyTarget.dir}
            </code>
            （关联键口径，与追踪表同源；卡片上的展示名可能与之不同）。方向、批次
            创建后不能在界面上修改，请一次填对。
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Select
              value={applyDraft.方向}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 方向: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="方向" />
              </SelectTrigger>
              <SelectContent>
                {DIRECTIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={applyDraft.批次}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 批次: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="批次" />
              </SelectTrigger>
              <SelectContent>
                {BATCHES.map((b) => (
                  <SelectItem key={b} value={b}>
                    {b}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={applyDraft.当前阶段}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 当前阶段: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder="当前阶段" />
              </SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-muted-foreground" htmlFor="apply-date">
              投递日期
            </label>
            <Input
              id="apply-date"
              type="date"
              className="w-40"
              value={applyDraft.投递日期}
              onChange={(e) =>
                setApplyDraft({ ...applyDraft, 投递日期: e.target.value })
              }
            />
          </div>
          <div className="flex gap-2">
            <Button onClick={submitApply} disabled={applying === applyTarget.dir}>
              {applying === applyTarget.dir && (
                <Loader2 size={14} className="animate-spin" />
              )}
              确认投递
            </Button>
            <Button variant="ghost" onClick={() => setApplyTarget(null)}>
              取消
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            {status ? "没有符合当前筛选的岗位" : "岗位池还是空的"}
          </p>
          <p className="mt-2 text-sm text-muted-foreground">
            {status
              ? "换个状态筛选看看，或把筛选切回「全部状态」。"
              : "点击「新建岗位」粘贴一份 JD，随后让 AI 生成解析卡，即可看到匹配度评分。"}
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((job) => (
            <JobCard
              key={job.dir}
              job={job}
              onOpen={() => open(job.dir)}
              onApply={() => startApply(job)}
              applying={applying === job.dir}
            />
          ))}
        </div>
      )}
    </div>
  );
}
