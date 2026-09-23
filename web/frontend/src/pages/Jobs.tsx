import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowDown, ArrowUp, Inbox, Loader2, Plus, Search } from "lucide-react";
import {
  api,
  BATCHES,
  DIRECTIONS,
  STAGES,
  type Application,
  type JobOrder,
  type JobSort,
  type JobStatus,
  type JobSummary,
} from "../api";
// 模块级常量表存 key 而不是文案，渲染处再翻（拼错的 key 编译期就报错）
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { domainLabel } from "../lib/domainLabels";
import { DRILL_KEY, drillToApplication } from "../lib/pageDrill";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { EmptyState } from "../components/ui/empty";
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { announce } from "../lib/announce";
import JobCard from "../components/JobCard";
import JobDetailView from "../components/JobDetailView";
import JobCreateForm from "../components/JobCreateForm";
import { Segmented } from "../components/ui/segmented";

// 四排序与后端 jobs.py 的 JOB_SORTS 白名单一致；未知键由后端静默回退 dir
const SORT_LABELS: Record<JobSort, TranslationKey> = {
  dir: "job.sortDir",
  score: "app.sortScore",
  state: "job.sortState",
  recent: "job.sortRecent",
};

// 每个维度的自然方向（与后端 JOB_DEFAULT_ORDER 同一张表）：
// 评分默认想看高分、最近更新默认想看新的，目录名默认 A→Z
const DEFAULT_ORDER: Record<JobSort, JobOrder> = {
  dir: "asc",
  score: "desc",
  state: "asc",
  recent: "desc",
};

const STATUS_ITEMS: { value: JobStatus; labelKey: TranslationKey }[] = [
  { value: "", labelKey: "job.allStatus" },
  { value: "unapplied", labelKey: "job.filterUnapplied" },
  { value: "active", labelKey: "job.filterActive" },
  { value: "terminal", labelKey: "job.filterTerminal" },
];

// Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达（与 Applications 同）
const ALL = "__all__";

// 下钻约定：键与写方统一走 lib/pageDrill（此前本地重写常量，改键时会静默漂掉）

function today(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/**
 * 目录名 → (公司, 岗位)。取首个下划线、两端 trim。
 *
 * **这不是权威实现，只是点击时的即时预检**（拆不出来就别让用户白填一屏）。
 * 真正写入追踪表的公司与岗位由后端按 `jobs._split_dir` 拆分——提交时只传目录名，
 * 所以两份实现即使漂了，写进去的也仍然是对的。
 */
function splitDir(dir: string): [string, string] {
  const i = dir.indexOf("_");
  return i < 0
    ? [dir.trim(), ""]
    : [dir.slice(0, i).trim(), dir.slice(i + 1).trim()];
}

export default function Jobs() {
  const [items, setItems] = useState<JobSummary[]>([]);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof api.jobDetail>> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const { t } = useTranslation();
  const [sort, setSort] = useState<JobSort>("dir");
  const [order, setOrder] = useState<JobOrder>("asc");
  const [status, setStatus] = useState<JobStatus>("");
  // FC-8（体检）：关键词搜索。输入框的值与真正去请求的值**分开**——
  // 岗位列表每条都要读一次解析卡（磁盘读），按键即请求会把键入变成一串 IO；
  // 300ms 防抖后再落到一个真正参与取数的 q 上。
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQ(qInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [qInput]);
  // 当前筛选项是个 labelKey（模块级常量存不下翻译后的字符串）。
  // **必须放在 status 声明之后**：放前面会踩 TDZ（`Cannot access 'status' before
  // initialization`），而 tsc 与 eslint 都拦不住——只有真正打开本页才会炸
  // （2026-09-12 冒烟前实测）。
  const statusLabelKey = STATUS_ITEMS.find((s) => s.value === status)?.labelKey;
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

  // 只看最后一次请求的结果：300ms 防抖之外仍可能乱序返回（改关键词后旧响应后到，
  // 会把新结果盖掉，列表与关键词对不上）。序号守卫即可，不动 http 层签名
  // （2026-09-22 审查 MINOR）。
  const loadSeq = useRef(0);

  const load = () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    api
      .listJobs({ sort, order, status, q })
      .then(
        (r) => {
          if (seq !== loadSeq.current) return; // 过期响应：丢弃
          setItems(r.items);
          setError(null); // 重新拉到数据就撤掉上一次的报错，别让旧错误条常驻
        },
        (e: Error) => {
          if (seq !== loadSeq.current) return;
          setError(e.message);
        }
      )
      .then(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
  };

  useEffect(load, [sort, order, status, q]);

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

  // 看板「高分未投」下钻：带 focusDir 进来时直接打开该岗位详情。
  // 读完即清——否则下次从导航回到岗位池会莫名其妙又弹一次详情。
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(DRILL_KEY);
      if (!raw) return;
      const drill = JSON.parse(raw) as { focusDir?: string };
      sessionStorage.removeItem(DRILL_KEY);
      if (drill.focusDir) open(drill.focusDir);
    } catch {
      // sessionStorage 不可用或内容坏了：当作没有下钻，不影响正常浏览
    }
  }, []);

  // 新建 / 抓取两条写入路径的结果都在父级落地（重拉列表、打开详情、播报一句）：
  // 表单自己只管草稿与请求，见 components/JobCreateForm.tsx
  const onCreated = (company: string, role: string) => {
    setCreating(false);
    load();
    // 与行编辑不同：新建是"整条记录凭空出现"，必须给读屏一句确认
    announce(t("job.created", { company, role }));
  };

  const onFetched = (dir: string, company: string, role: string) => {
    setCreating(false);
    load();
    // 抓取成功后后端已写入 JD原文.md，直接打开详情让用户核对原文——
    // 抓取只是省掉复制粘贴，内容仍必须由用户过目（不做任何改写或摘要）
    open(dir);
    announce(t("job.created", { company, role }));
  };

  // 换维度就回到该维度的自然方向：评分默认想看高分，目录名默认想看 A→Z
  const changeSort = (key: JobSort) => {
    setSort(key);
    setOrder(DEFAULT_ORDER[key]);
  };

  const startApply = (job: JobSummary) => {
    if (applying) return; // 已有投递在飞行中，先等它落地
    const [company, role] = splitDir(job.dir);
    // 公司与岗位都要非空：只查 role 时，目录名以「_」开头会写出一条空公司的记录，
    // 而后端建索引会跳过空键 → 追踪表里有记录、岗位池永远显示「未投递」
    if (!company || !role) {
      setError(
        t("job.splitDirFailed", { dir: job.dir })
      );
      return;
    }
    setError(null);
    setApplyTarget(job);
  };

  // 提交只传**目录名**：公司与岗位由后端按同一口径拆分（匹配键只有一处来源），
  // 评分也原样传（解析卡的维度分可能是小数），取整同样在后端做。
  // 两件事都不在这里做，正是为了不让同一个规则在客户端多出一份。
  const submitApply = () => {
    if (!applyTarget) return;
    setApplying(applyTarget.dir);
    setError(null);
    const payload: Partial<Application> & { 岗位目录?: string } = {
      岗位目录: applyTarget.dir,
      ...applyDraft,
    };
    // **未评分时不传**——「没有评分」不等于「0 分」，留空才诚实
    if (applyTarget.score !== null) {
      payload.评分 = String(applyTarget.score);
    }
    api
      .addApplication(payload)
      .then((r) => {
        setApplying(null);
        setApplyTarget(null);
        // 跳追踪表并展开新行：写方统一在 lib/pageDrill（与看板同一套约定）
        drillToApplication(r.id);
      })
      .catch((e: Error) => {
        // 失败一律把后端文案直出（409 重复录入也是人话），确认卡保持打开方便改了重试
        setError(e.message);
        setApplying(null);
      });
  };

  // 空态文案在这里分支（避免三层嵌套三元）：搜索无匹配 ≠ 筛选筛空了 ≠ 岗位池本来就空，
  // 三者要说清各自"下一步"（2026-09-22 审查 MINOR）。
  const emptyCopy = (() => {
    if (q) {
      return { title: t("job.emptySearch", { q }), hint: t("job.emptySearchHint") };
    }
    if (status) {
      return {
        title: t("job.emptyFiltered"),
        hint: t("job.emptyFilteredHint", { all: t("job.allStatus") }),
      };
    }
    return {
      title: t("job.emptyPool"),
      hint: t("job.emptyPoolHint", { action: t("job.newJob") }),
    };
  })();

  if (detail) {
    return (
      <JobDetailView detail={detail} expanded={expanded}
        onToggleDimension={(name) => setExpanded(expanded === name ? null : name)}
        onBack={closeDetail}
        // 删除 / 改名后：详情引用的目录已变，关详情并重拉列表
        onChanged={() => { closeDetail(); load(); }}
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
    <div className="space-y-6">
      <PageHeader title={t("nav.jobs")} />

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          {t("job.count", { count: items.length })}
          {status && statusLabelKey ? t("job.filteredBy", { name: t(statusLabelKey) }) : ""}
          {t("job.scoreHint")}
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> {t("job.newJob")}
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          {/* FC-8（体检）：与追踪表同款搜索框——能看到「什么被筛掉了」之外，
              还得能按公司 / 岗位直接找。aria-label 复用占位文案：
              只给 placeholder 的搜索框在部分读屏上名字是空的 */}
          <div className="relative w-48">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              value={qInput}
              onChange={(event) => setQInput(event.target.value)}
              placeholder={t("job.searchPlaceholder")}
              aria-label={t("job.searchPlaceholder")}
              className="h-9 pl-8 text-xs"
            />
          </div>

          {/* 分段控件与简历工坊的模式切换条同一形态：原先的文字按钮 + 双向箭头
              既看不出当前选中谁，也放不下「顺序 / 逆序」这半个控制。
              2026-09-13 起改用 ui/segmented（原生 radio group）：Tabs 当单选开关用
              会挂上不存在的 aria-controls，axe 拦得住、语义也是错的 */}
          <Segmented
            value={sort}
            onChange={(v) => changeSort(v)}
            ariaLabel={t("job.sortAria")}
            options={(Object.keys(SORT_LABELS) as JobSort[]).map((key) => ({
              value: key,
              label: t(SORT_LABELS[key]),
            }))}
          />

          <Button
            variant="outline"
            className="h-9 gap-1.5 px-3 text-xs"
            onClick={() => setOrder((o) => (o === "asc" ? "desc" : "asc"))}
            title={t(order === "asc" ? "job.orderHintAsc" : "job.orderHintDesc")}
          >
            {order === "asc" ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
            {order === "asc" ? t("job.asc") : t("job.desc")}
          </Button>
        </div>
        <Select
          value={status === "" ? ALL : status}
          onValueChange={(v) => setStatus(v === ALL ? "" : (v as JobStatus))}
        >
          <SelectTrigger className="w-32" aria-label={t("job.filterStatus")}>
            <SelectValue placeholder={t("job.allStatus")} />
          </SelectTrigger>
          <SelectContent>
            {STATUS_ITEMS.map((s) => (
              <SelectItem key={s.value || ALL} value={s.value || ALL}>
                {t(s.labelKey)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {creating && (
        <JobCreateForm
          onCreated={onCreated}
          onFetched={onFetched}
          onError={setError}
          onClose={() => setCreating(false)}
        />
      )}

      {applyTarget && (
        <Card className="space-y-3 border-primary/30 p-5">
          <p className="text-sm font-medium text-foreground">
            {t("job.confirmApply", {
              company: applyTarget.company,
              role: applyTarget.role,
            })}
          </p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("job.applyNoteA")}{" "}
            <code className="rounded bg-background px-1 py-0.5 text-foreground">
              {applyTarget.dir}
            </code>
            {t("job.applyNoteB")}
          </p>
          <div className="grid gap-3 sm:grid-cols-3">
            <Select
              value={applyDraft.方向}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 方向: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder={t("form.phDirection")} />
              </SelectTrigger>
              <SelectContent>
                {DIRECTIONS.map((d) => (
                  <SelectItem key={d} value={d}>
                    {domainLabel("direction", d, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={applyDraft.批次}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 批次: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder={t("form.phBatch")} />
              </SelectTrigger>
              <SelectContent>
                {BATCHES.map((b) => (
                  <SelectItem key={b} value={b}>
                    {domainLabel("batch", b, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={applyDraft.当前阶段}
              onValueChange={(v) => setApplyDraft({ ...applyDraft, 当前阶段: v })}
            >
              <SelectTrigger>
                <SelectValue placeholder={t("form.phStage")} />
              </SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {domainLabel("stage", s, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-xs text-muted-foreground" htmlFor="apply-date">
              {t("job.applyDate")}
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
              {t("job.confirmApplyBtn")}
            </Button>
            <Button variant="ghost" onClick={() => setApplyTarget(null)}>
              {t("common.cancel")}
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
        <Card>
          {/* 三种空态分开说：搜索无匹配 ≠ 筛选筛空了 ≠ 岗位池本来就空。
              原先搜索无命中会落到「岗位池还是空的」，是误导性提示（2026-09-22 审查 MINOR） */}
          <EmptyState
            icon={<Inbox size={20} />}
            title={emptyCopy.title}
            description={emptyCopy.hint}
          />
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
              busy={applying !== null}
            />
          ))}
        </div>
      )}
    </div>
  );
}
