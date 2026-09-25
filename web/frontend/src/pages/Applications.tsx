import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp, Inbox, Mail, Plus, Search, X } from "lucide-react";
import {
  api,
  BATCHES,
  DIRECTIONS,
  SOURCES,
  type Application,
  type HistoryEntry,
} from "../api";
import { NONE, readDrill, type SortKey } from "../lib/applicationMeta";
import { formatMailDate } from "../lib/date";
import { DRILL_KEY } from "../lib/pageDrill";
import { useJobDirs } from "../hooks/useJobDirs";
import { useMissingNext } from "../hooks/useMissingNext";
import { domainLabel } from "../lib/domainLabels";
import ApplicationFilters from "../components/ApplicationFilters";
import ApplicationsTable from "../components/ApplicationsTable";
import ImportApplicationsDialog from "../components/ImportApplicationsDialog";
import ImapFetchDialog from "../components/ImapFetchDialog";
import StatusUpdateDialog from "../components/StatusUpdateDialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { EmptyState } from "../components/ui/empty";
import { announce } from "../lib/announce";
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";


export default function Applications() {
  const { t } = useTranslation();
  const drill = useMemo(readDrill, []);
  const [items, setItems] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  // 搜索词不进 filter：它有防抖后的 `q`，两个来源会飘。
  const [filter, setFilter] = useState({
    stage: drill.stage ?? "",
    direction: drill.direction ?? "",
    batch: drill.batch ?? "",
  });
  const [sort, setSort] = useState<SortKey>(drill.sort ?? "next");
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showImport, setShowImport] = useState(false);
  const [showStatus, setShowStatus] = useState(false);
  const [showImap, setShowImap] = useState(false);
  // IMAP 选中的邮件正文：交给 StatusUpdateDialog 预填（用户仍可编辑再解析）
  const [statusDraft, setStatusDraft] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [timelines, setTimelines] = useState<Record<string, HistoryEntry[]>>({});
  const [draft, setDraft] = useState({
    公司: "",
    岗位: "",
    方向: "hvac",
    批次: "正式批",
    来源: "",
    链接: "",
    评分: 60,
    截止日期: "",
    当前阶段: "待投",
  });
  const { showMissingOnly, setShowMissingOnly, missingNext, visibleItems } =
    useMissingNext(items);

  // 输入框的值与真正去取数的值**分开**（同 Jobs 的 FC-8 口径）：每敲一个字就把
  // filter 换成新对象会立刻触发一次列表请求（每条记录都要读磁盘），键入变成一串 IO。
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setQ(qInput.trim()), 300);
    return () => clearTimeout(timer);
  }, [qInput]);

  // 序号守卫：300ms 防抖之外仍可能乱序返回（旧响应后到会把新列表盖掉，
  // 于是列表与搜索框里的关键词对不上）。写法与 Jobs.load 同源
  const loadSeq = useRef(0);

  const load = () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    api
      .listApplications({
        stage: filter.stage,
        direction: filter.direction,
        batch: filter.batch,
        q,
        sort,
      })
      .then(
        (r) => {
          if (seq !== loadSeq.current) return;
          setItems(r.items);
          // 若下钻带 focusId，自动展开并滚动到该行
          if (drill.focusId) {
            const focusId = drill.focusId;
            setExpanded((prev) => ({ ...prev, [focusId]: true }));
            // 承诺了"滚动到该行"就得真的滚：表格是内部滚动容器（max-h + overflow-auto），
            // 目标行常在可视区之外；只展开不滚动时用户看不出下钻落到了哪一条，而
            // `row-{id}` 锚点此前全仓没有任何消费者（2026-09-23 二轮审计）
            requestAnimationFrame(() => {
              document.getElementById(`row-${focusId}`)?.scrollIntoView({ block: "center" });
            });
          }
          setError(null);
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

  // 依赖里放 `filter` 的字段而不是整个对象：`q` 已由上面的防抖单独负责，
  // 否则每敲一个字都会重新拉一次列表
  useEffect(load, [filter.stage, filter.direction, filter.batch, q, sort, drill]);
  // 下钻筛选只生效一次：首次加载后清掉，避免重复返回看板时的旧筛选残留
  useEffect(() => {
    sessionStorage.removeItem(DRILL_KEY);
  }, []);

  // UX-3（体检）：岗位池目录名反查表，供行内「查看解析卡」入口使用
  const jobDirs = useJobDirs();

  // 返回是否写入成功：行内输入（状态原因 / 下次动作日期）是 uncontrolled，失败时
  // 要能据此把 DOM 值回滚成服务端真值（见 ApplicationRow 的 commitInline）
  const patch = (id: string, body: Partial<Application>) =>
    api
      .updateApplication(id, body)
      .then(() => {
        load();
        return true;
      })
      .catch((e: Error) => {
        setError(e.message);
        return false;
      });

  const submit = () => {
    api
      .addApplication({ ...draft, 评分: String(draft.评分) })
      .then(() => {
        setCreating(false);
        // UX-6：写入成功只体现在表格里多了一行，读屏用户听不到——播报一句
        announce(t("app.created", { company: draft.公司, role: draft.岗位 }));
        setDraft({
          公司: "",
          岗位: "",
          方向: "hvac",
          批次: "正式批",
          来源: "",
          链接: "",
          评分: 60,
          截止日期: "",
          当前阶段: "待投",
        });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  const toggleTimeline = (id: string) => {
    const next = { ...expanded, [id]: !expanded[id] };
    setExpanded(next);
    if (next[id] && !timelines[id]) {
      api
        .applicationHistory(id)
        .then((h) => setTimelines((prev) => ({ ...prev, [id]: h.items })))
        .catch((e: Error) => setError(e.message));
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t("nav.applications")} />

      {error && (
        <div className="flex items-center justify-between rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative w-56">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder={t("app.searchPlaceholder")}
            className="pl-8"
          />
        </div>

        <ApplicationFilters value={filter} onChange={setFilter} />

        <Button variant="outline" onClick={() => setShowStatus(true)}>
          <Mail size={15} /> {t("app.pasteMail")}
        </Button>

        <Button variant="outline" onClick={() => setShowImap(true)}>
          <Inbox size={15} /> {t("app.fetchMail")}
        </Button>

        <Button variant="outline" onClick={() => setShowImport(true)}>
          <FileUp size={15} /> {t("app.importCsv")}
        </Button>

        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> {t("app.newApplication")}
        </Button>
      </div>

      {/* 「没有下一步动作」引导（A7）：把缺项摆到眼前，一键切到筛选视图 */}
      {!loading && missingNext.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-xs">
          <span className="text-foreground">
            {t("app.missingNextHint", { count: missingNext.length })}
          </span>
          <button
            onClick={() => setShowMissingOnly((v) => !v)}
            className="cursor-pointer font-medium text-primary hover:underline"
          >
            {showMissingOnly ? t("app.showAllRecords") : t("app.filterMissingNext")}
          </button>
        </div>
      )}

      {showImport && (
        <ImportApplicationsDialog
          onClose={() => setShowImport(false)}
          onImported={load}
        />
      )}

      {showImap && (
        <ImapFetchDialog
          onClose={() => setShowImap(false)}
          onUse={(body) => {
            // 不在这里解析：预填原文，走同一条「解析 → 确认」流程。
            // **拉取框保持挂载**，二级对话框叠在它上面——用户从二级点取消 / 关掉时
            // 要回到原来的邮件列表与位置，而不是连列表一起被关掉（2026-09-25 真机：
            // 此前这里先 setShowImap(false)，回头无路，而且重开会重连邮箱）。
            setStatusDraft(body);
            setShowStatus(true);
          }}
          onRecord={(m) =>
            // 只沉淀元数据，不解析、不改任何投递阶段；标签/关联在「进展 → 邮件」里补。
            // 日期口径统一走 lib/date（RFC 2822 → CSV 的 `YYYY-MM-DD HH:mm`）：此前这里
            // 与「解析建议」那条链路各写一套，其中一套漏了转换（2026-09-25 真机）。
            api.createMail({
              消息id: m.messageId ?? "",
              主题: m.subject,
              发件人: m.from,
              日期: formatMailDate(m.date),
            })
          }
        />
      )}

      {showStatus && (
        <StatusUpdateDialog
          // key 显式化「初始值只读一次」的契约（issue #50 m3）：换 draft 就换实例，
          // 而不是让组件静默沿用上一次的原文（那会把邮件写进另一条记录）
          key={statusDraft}
          applications={items}
          onClose={() => {
            setShowStatus(false);
            setStatusDraft("");
          }}
          onApplied={load}
          initialText={statusDraft}
        />
      )}

      {creating && (
        <div className="rounded-lg border border-primary/30 bg-card/70 shadow-card ring-1 ring-highlight/5 p-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <Input
              placeholder={t("form.phCompany")}
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <Input
              placeholder={t("form.phRole")}
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
            <Select
              value={draft.方向}
              onValueChange={(v) => setDraft({ ...draft, 方向: v })}
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
              value={draft.批次}
              onValueChange={(v) => setDraft({ ...draft, 批次: v })}
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
            <Input
              type="date"
              value={draft.截止日期}
              onChange={(e) => setDraft({ ...draft, 截止日期: e.target.value })}
            />
            <Input
              type="number"
              min={0}
              max={100}
              value={draft.评分}
              onChange={(e) =>
                setDraft({ ...draft, 评分: Number(e.target.value) })
              }
            />
            {/* 来源可选：空值用哨兵表达（Radix 不接受空字符串 value），
                真值为空时落库仍写空串——与 CLI 不加 --source 的行为一致 */}
            <Select
              value={draft.来源 || NONE}
              onValueChange={(v) =>
                setDraft({ ...draft, 来源: v === NONE ? "" : v })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder={t("form.phSource")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t("form.sourceNone")}</SelectItem>
                {SOURCES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {domainLabel("source", s, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              type="url"
              placeholder={t("form.phUrl")}
              value={draft.链接}
              onChange={(e) => setDraft({ ...draft, 链接: e.target.value })}
              onBlur={() => {
                // 粘贴岗位页 URL 后离开输入框时做本地推断（A5）：补全 scheme，
                // 并在用户尚未选来源时预填。推断失败静默——它是助手，不打扰。
                const raw = draft.链接.trim();
                if (!raw) return;
                api
                  .inferUrl(raw)
                  .then((r) => {
                    if (!r.ok) return;
                    setDraft((prev) => ({
                      ...prev,
                      链接: r.链接 || prev.链接,
                      来源: prev.来源 || r.来源,
                    }));
                  })
                  .catch((e: Error) => {
                    // 推断失败不打扰用户（来源本就允许手填），但按「禁静默吞错」
                    // 留一条控制台日志，便于排查后端不可用这类系统性问题。
                    console.error("inferUrl failed", e);
                  });
              }}
            />
          </div>
          <div className="mt-4 flex gap-2">
            <Button
              onClick={submit}
              disabled={!draft.公司.trim() || !draft.岗位.trim()}
            >
              {t("common.save")}
            </Button>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              {t("common.cancel")}
            </Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-2 rounded-lg border border-border p-4">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-10 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        // 加载失败时**不显示空态**：把「接口挂了 / 参数被拒」渲染成「没有记录」，
        // 用户会以为数据丢了（其余六处列表都有 `!error &&` 守卫，这两页此前漏了）
        error ? null : (
          <div className="rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-highlight/5">
            <EmptyState
              icon={<Inbox size={20} />}
              title={t("app.emptyTitle")}
              description={t("app.emptyHint", { action: t("app.newApplication") })}
            />
          </div>
        )
      ) : (
        <ApplicationsTable
          items={visibleItems}
          sort={sort}
          onSortChange={setSort}
          expanded={expanded}
          timelines={timelines}
          onToggleTimeline={toggleTimeline}
          onPatch={patch}
          onReload={load}
          jobDirs={jobDirs}
        />
      )}
    </div>
  );
}
