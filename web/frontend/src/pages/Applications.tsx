import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp, Inbox, Mail, Plus, Search, X } from "lucide-react";
import {
  api,
  BATCHES,
  DIRECTIONS,
  SOURCES,
  STAGES,
  TERMINAL,
  type Application,
  type HistoryEntry,
} from "../api";
import { ALL, NONE, readDrill, type SortKey } from "../lib/applicationMeta";
import { domainLabel } from "../lib/domainLabels";
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
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";


export default function Applications() {
  const { t } = useTranslation();
  const drill = useMemo(readDrill, []);
  const [items, setItems] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState({
    stage: drill.stage ?? "",
    direction: drill.direction ?? "",
    batch: drill.batch ?? "",
    q: "",
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
  // 「没有下一步动作」引导（v0.4.0-A）：进行中（非终态）但没填「下次动作」的记录
  const [showMissingOnly, setShowMissingOnly] = useState(false);
  const missingNext = useMemo(
    () =>
      items.filter(
        (it) => !TERMINAL.includes(it.当前阶段) && !(it.下次动作 || "").trim()
      ),
    [items]
  );
  // 全部补齐后自动退出「只看缺下一步」视图，避免停在空表格上
  useEffect(() => {
    if (showMissingOnly && missingNext.length === 0) setShowMissingOnly(false);
  }, [showMissingOnly, missingNext.length]);
  const visibleItems = showMissingOnly ? missingNext : items;

  const load = () => {
    setLoading(true);
    api
      .listApplications({ ...filter, sort })
      .then(
        (r) => {
          setItems(r.items);
          // 若下钻带 focusId，自动展开并滚动到该行
          if (drill.focusId) {
            setExpanded((prev) => ({ ...prev, [drill.focusId!]: true }));
          }
        },
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  };

  // drill 是 useMemo([]) 的稳定引用，focusId 在生命周期内不变——
  // 放进依赖只是让 lint 满意，不会造成重复触发
  useEffect(load, [filter, sort, drill]);
  // 下钻筛选只生效一次：首次加载后清掉，避免重复返回看板时的旧筛选残留
  useEffect(() => {
    sessionStorage.removeItem("jobws_drill");
  }, []);

  const patch = (id: string, body: Partial<Application>) => {
    api
      .updateApplication(id, body)
      .then(() => load())
      .catch((e: Error) => setError(e.message));
  };

  const submit = () => {
    api
      .addApplication({ ...draft, 评分: String(draft.评分) })
      .then(() => {
        setCreating(false);
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
            value={filter.q}
            onChange={(e) => setFilter({ ...filter, q: e.target.value })}
            placeholder={t("app.searchPlaceholder")}
            className="pl-8"
          />
        </div>

        {/* Radix Select 不接受空字符串作为 value，「全部」用哨兵值表达 */}
        <Select
          value={filter.stage || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, stage: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-36" aria-label={t("app.filterStage")}>
            <SelectValue placeholder={t("app.allStages")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("app.allStages")}</SelectItem>
            {STAGES.map((s) => (
              <SelectItem key={s} value={s}>
                {domainLabel("stage", s, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filter.direction || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, direction: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-32" aria-label={t("app.filterDirection")}>
            <SelectValue placeholder={t("app.allDirections")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("app.allDirections")}</SelectItem>
            {DIRECTIONS.map((d) => (
              <SelectItem key={d} value={d}>
                {domainLabel("direction", d, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filter.batch || ALL}
          onValueChange={(v) =>
            setFilter({ ...filter, batch: v === ALL ? "" : v })
          }
        >
          <SelectTrigger className="w-32" aria-label={t("app.filterBatch")}>
            <SelectValue placeholder={t("app.allBatches")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t("app.allBatches")}</SelectItem>
            {BATCHES.map((b) => (
              <SelectItem key={b} value={b}>
                {domainLabel("batch", b, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

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
            // 不在这里解析：关闭拉取框、预填原文，走同一条「解析 → 确认」流程
            setShowImap(false);
            setStatusDraft(body);
            setShowStatus(true);
          }}
          onRecord={(m) => {
            const parsed = new Date(m.date);
            const pad = (n: number) => String(n).padStart(2, "0");
            // IMAP 的 Date 头是 RFC 5322 原文（"Tue, 16 Sep ..."）——转成 CSV 既有的
            // 「YYYY-MM-DD HH:MM」再落库，否则与手工行混排后「日期倒序」失序（审查 m-1）；
            // 解析失败保留原文（诚实展示，仅排序降级）。
            const date = isNaN(parsed.getTime())
              ? m.date
              : `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ` +
                `${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
            // 只沉淀元数据，不解析、不改任何投递阶段；标签/关联在「进展 → 邮件」里补。
            return api.createMail({
              消息id: m.messageId ?? "",
              主题: m.subject,
              发件人: m.from,
              日期: date,
            });
          }}
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
        <div className="rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-highlight/5">
          <EmptyState
            icon={<Inbox size={20} />}
            title={t("app.emptyTitle")}
            description={t("app.emptyHint", { action: t("app.newApplication") })}
          />
        </div>
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
        />
      )}
    </div>
  );
}
