// 投递追踪表单行（H-2b 批自 pages/Applications.tsx 拆出）：主行 + 展开行
// （时间线 / 关联邮件 / 删除）。受控组件——数据与动作全由表格容器传入。
import { ChevronDown, ChevronRight, ExternalLink } from "lucide-react";
import { useTranslation } from "react-i18next";
import { STAGES, TERMINAL, type Application, type HistoryEntry } from "../api";
import { HEALTH_META, STALE_DAYS, stageStyle } from "../lib/applicationMeta";
import { domainLabel } from "../lib/domainLabels";
import { reasonLines } from "../lib/healthReasons";
import { previewDeleteApplication } from "../lib/records";
import DeleteRecordButton from "./DeleteRecordButton";
import HistoryTimeline from "./HistoryTimeline";
import RecordMails from "./RecordMails";
import { Num } from "./ui/number";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

type Props = {
  it: Application;
  isExpanded: boolean;
  timeline: HistoryEntry[];
  onToggleTimeline: () => void;
  onPatch: (body: Partial<Application>) => void;
  onReload: () => void;
};

export default function ApplicationRow({
  it,
  isExpanded,
  timeline,
  onToggleTimeline,
  onPatch,
  onReload,
}: Props) {
  const { t } = useTranslation();
  const staleDays = typeof it.stageDays === "number" ? it.stageDays : null;
  const isStale = staleDays !== null && staleDays >= STALE_DAYS;
  return (
    <>
      <tr
        id={`row-${it.id}`}
        className="group bg-card/40 shadow-card ring-1 ring-highlight/5 transition-colors hover:bg-secondary"
      >
        <td className="border-l-2 border-transparent px-4 py-3 transition-colors group-hover:border-primary">
          <button
            onClick={onToggleTimeline}
            className="mr-2 inline-flex cursor-pointer align-middle text-muted-foreground transition-colors hover:text-primary"
            title={t(isExpanded ? "app.collapseTimeline" : "app.expandTimeline")}
          >
            {isExpanded ? (
              <ChevronDown size={14} />
            ) : (
              <ChevronRight size={14} />
            )}
          </button>
          <span className="font-medium text-foreground">
            {it.公司 || "—"}
          </span>
          <div className="pl-6 text-xs text-muted-foreground">
            {it.岗位 || t("app.roleMissing")}
          </div>
          {/* 岗位链接：有链接才出现，不新增一整列（表宽已经不小）；
              新标签打开，避免把追踪表上下文顶掉 */}
          {it.链接 && (
            <a
              href={it.链接}
              target="_blank"
              rel="noreferrer"
              title={t("app.openLink")}
              aria-label={t("app.openLink")}
              className="ml-6 mt-0.5 inline-flex items-center gap-1 text-xs text-foreground underline underline-offset-2 transition-colors hover:text-primary"
            >
              <ExternalLink size={11} />
              {t("app.jobLink")}
            </a>
          )}
        </td>
        <td className="px-4 py-3 text-foreground">
          {it.方向 ? domainLabel("direction", it.方向, t) : "—"}
        </td>
        <td className="px-4 py-3 text-foreground">
          {it.批次 ? domainLabel("batch", it.批次, t) : "—"}
        </td>
        <td className="px-4 py-3">
          {TERMINAL.includes(it.当前阶段) ? (
            <div className="flex flex-col gap-0.5">
              <span
                className={`rounded-md px-2 py-1 text-xs font-medium ${stageStyle(
                  it.当前阶段
                )}`}
              >
                {domainLabel("stage", it.当前阶段, t)}
              </span>
              <span className="text-[10px] text-muted-foreground">
                {t("app.terminalLocked")}
              </span>
            </div>
          ) : (
            <Select
              value={it.当前阶段}
              onValueChange={(v) => onPatch({ 当前阶段: v })}
            >
              <SelectTrigger
                // 行内阶段编辑器：可视文本是阶段取值，而 role=combobox
                // 按 ARIA 不能从内容取名字，必须显式给 aria-label；
                // 且每行都长得一样——名字里带上公司与岗位，屏幕阅读器
                // 才分得清是哪一条投递（独立审查提出）
                aria-label={t("app.stageEditorAria", {
                  company: it.公司,
                  role: it.岗位,
                })}
                className={`h-auto w-auto cursor-pointer gap-2 rounded-md border-0 px-2 py-1 text-xs font-medium shadow-none ${stageStyle(
                  it.当前阶段
                )}`}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => (
                  <SelectItem key={s} value={s} className="text-xs">
                    {domainLabel("stage", s, t)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </td>
        <td className="px-4 py-3">
          <input
            defaultValue={it.状态原因}
            onBlur={(e) => {
              if (e.target.value !== it.状态原因) {
                onPatch({ 状态原因: e.target.value });
              }
            }}
            placeholder={
              TERMINAL.includes(it.当前阶段) ? t("app.reasonRequired") : t("app.reasonOptional")
            }
            className="w-full min-w-[8rem] rounded border border-transparent bg-transparent px-2 py-1 text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground hover:border-border-strong focus:border-primary/50"
          />
        </td>
        <td className="px-4 py-3">
          <input
            defaultValue={it.下次动作日期}
            onBlur={(e) => {
              if (e.target.value !== it.下次动作日期) {
                onPatch({ 下次动作日期: e.target.value });
              }
            }}
            type="date"
            title={t("app.sortNext")}
            className="w-36 rounded border border-transparent bg-transparent px-2 py-1 font-mono text-xs text-foreground outline-none transition-colors hover:border-border-strong focus:border-primary/50"
          />
          <div className="pl-2 text-xs text-muted-foreground">
            {it.下次动作 || "—"}
          </div>
        </td>
        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
          {it.截止日期 || "—"}
        </td>
        <td className="px-4 py-3 text-right">
          <Num align="right" className="text-xs">
            {it.评分 || "—"}
          </Num>
        </td>
        <td className="px-4 py-3">
          {staleDays !== null ? (
            <Num
              className={`inline-flex items-center gap-1 text-xs ${
                isStale ? "text-warning" : "text-muted-foreground"
              }`}
            >
              {isStale && (
                <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              )}
              {t("app.daysUnit", { count: staleDays })}
            </Num>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-4 py-3">
          {(() => {
            const h = it.health;
            if (!h || !h.level) {
              return <span className="text-xs text-muted-foreground">—</span>;
            }
            const meta = HEALTH_META[h.level];
            return (
              <span
                title={
                  reasonLines(h.reasons, h.hints, t).join(t("app.reasonJoiner")) ||
                  t("app.noHealthIssue")
                }
                className={`cursor-help rounded-md px-2 py-1 text-xs font-medium ${meta.cls}`}
              >
                {t(meta.labelKey)}
              </span>
            );
          })()}
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-background/60">
          <td
            colSpan={10}
            className="border-l-2 border-primary/30 px-6 py-4"
          >
            <HistoryTimeline entries={timeline} />
            {/* 关联邮件（2026-09-17 收尾批）：批 4.5 承诺过的
                「投递详情显示关联邮件」——只读 + 打开原邮件；
                增 / 改 / 删在「进展 → 邮件」的台账里做 */}
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-xs font-medium text-foreground">
                {t("app.relatedMails")}
              </p>
              <RecordMails appId={it.id} />
            </div>
            {/* 删除（批 D）：预览（含「将解绑的关联记录」清单）→
                确认弹窗 → 凭令牌落盘 */}
            <div className="mt-4 border-t border-border pt-3">
              <DeleteRecordButton
                preview={() => previewDeleteApplication(it.id)}
                onDeleted={onReload}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
