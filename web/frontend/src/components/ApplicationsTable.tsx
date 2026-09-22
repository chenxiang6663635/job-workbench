// 投递追踪表容器（H-2b 批自 pages/Applications.tsx 拆出）：粘性表头 + 行映射。
// 受控组件——筛选 / 排序 / 展开态与数据动作全部来自页面，这里不自己取数。
import { ChevronsUpDown } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Application, HistoryEntry } from "../api";
import { SORT_LABELS, type SortKey } from "../lib/applicationMeta";
import ApplicationRow from "./ApplicationRow";

type Props = {
  items: Application[];
  sort: SortKey;
  onSortChange: (key: SortKey) => void;
  expanded: Record<string, boolean>;
  timelines: Record<string, HistoryEntry[]>;
  onToggleTimeline: (id: string) => void;
  onPatch: (id: string, body: Partial<Application>) => void;
  onReload: () => void;
  /** UX-3：投递 id → 岗位池目录名（由后端关联给出）。没有对应岗位的行不显示入口 */
  jobDirs: Record<string, string>;
};

export default function ApplicationsTable({
  items,
  sort,
  onSortChange,
  expanded,
  timelines,
  onToggleTimeline,
  onPatch,
  onReload,
  jobDirs,
}: Props) {
  const { t } = useTranslation();

  const sortBtn = (key: SortKey) => {
    const active = sort === key;
    return (
      <button
        onClick={() => onSortChange(active ? "next" : key)}
        className={`flex cursor-pointer items-center gap-1 font-medium transition-colors ${
          active
            ? "text-foreground underline underline-offset-2"
            : "text-muted-foreground hover:text-foreground"
        }`}
        title={t("app.sortByHint", { name: t(SORT_LABELS[key]) })}
      >
        {t(SORT_LABELS[key])}
        <ChevronsUpDown size={12} className={active ? "opacity-100" : "opacity-40"} />
      </button>
    );
  };

  /* 撑满 + 内部滚动 + 粘性纯色表头（批 4 编排总则）：表格是主内容区，
     容器吃掉视口剩余高度、长表在内部滚动；表头必须纯色——半透明会
     透出滚动内容，是粘性表头的经典事故。 */
  /* max-h 偏移：19 → 22.25rem——2026-09-17 新增页头（约 3.25rem）后同步，
     否则表格底部会被页头挤进来的高度盖住。这类魔法偏移正在被逐页算法化
     （Progress 页的 17rem 同样待后续批处理）。 */
  return (
    <div className="max-h-[calc(100dvh-22.25rem)] overflow-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 z-10 bg-surface-2 text-xs uppercase tracking-wider text-muted-foreground">
          <tr>
            <th className="px-4 py-3 text-left font-medium">{t("app.colCompanyRole")}</th>
            <th className="px-4 py-3 text-left font-medium">{t("app.colDirection")}</th>
            <th className="px-4 py-3 text-left font-medium">{t("app.colBatch")}</th>
            <th className="px-4 py-3 text-left font-medium">{t("app.colStage")}</th>
            <th className="px-4 py-3 text-left font-medium">{t("app.colReason")}</th>
            <th className="px-4 py-3 text-left font-medium">
              <span className="inline-flex items-center gap-1">
                {sortBtn("next")}
              </span>
            </th>
            <th className="px-4 py-3 text-left font-medium">{t("app.colDeadline")}</th>
            <th className="px-4 py-3 text-right font-medium">
              <span className="inline-flex items-center gap-1">
                {sortBtn("score")}
              </span>
            </th>
            <th className="px-4 py-3 text-left font-medium">
              <span className="inline-flex items-center gap-1">
                {sortBtn("stale")}
              </span>
            </th>
            <th className="px-4 py-3 text-left font-medium">
              <span className="inline-flex items-center gap-1">
                {sortBtn("health")}
              </span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {items.map((it) => (
            <ApplicationRow
              key={it.id}
              it={it}
              isExpanded={!!expanded[it.id]}
              timeline={timelines[it.id] ?? []}
              onToggleTimeline={() => onToggleTimeline(it.id)}
              onPatch={(body) => onPatch(it.id, body)}
              onReload={onReload}
              jobDir={jobDirs[it.id]}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}
