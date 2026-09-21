import { useEffect, useMemo, useState } from "react";
import { BookOpen, Download, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type BankQuestion } from "../api";
import { AskedBefore } from "./AskedBefore";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import { QuestionBankRow } from "./QuestionBankRow";
import { QuestionDetailDialog } from "./QuestionDetailDialog";

const BANK_STATUS = ["未看", "看过", "会了"];

function MyBank() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<BankQuestion[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 详情（也就是编辑）弹窗：null = 关闭，否则为被打开的那一行
  const [selected, setSelected] = useState<BankQuestion | null>(null);
  const [preview, setPreview] = useState<{ token: string; summary: string; diff: string[] } | null>(
    null
  );
  const [importing, setImporting] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    api
      .bankQuestions({ q: keyword.trim() || undefined, status: status || undefined })
      .then((r) => {
        setRows(r.items);
        setTotal(r.total);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  // 防抖：关键词每敲一下就打接口不划算；筛选变化则立即重载
  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, status]);

  const onPreviewImport = () => {
    setError(null);
    setImporting(true);
    api
      .previewQuestionImport()
      .then((r) => setPreview({ token: r.token, summary: r.summary, diff: r.diff }))
      .catch((e: Error) => setError(e.message))
      .finally(() => setImporting(false));
  };

  const onConfirmImport = () => {
    if (!preview) return;
    setImporting(true);
    setError(null);
    // 两段式的第二步：凭令牌落盘（与命令行 / MCP 同源，冲突与过期由服务端拒绝）
    api
      .applyApproval(preview.token)
      .then(() => {
        setPreview(null);
        load();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setImporting(false));
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder={t("bank.searchPlaceholder")}
            aria-label={t("bank.searchPlaceholder")}
            className="pl-9"
          />
        </div>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="h-9 rounded-lg border border-border bg-surface-1 px-2 text-xs text-foreground"
          aria-label={t("bank.statusFilter")}
        >
          <option value="">{t("bank.allStatus")}</option>
          {BANK_STATUS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <Button variant="outline" size="sm" onClick={onPreviewImport} disabled={importing}>
          <Download size={13} className="mr-1" />
          {importing ? t("bank.importing") : t("bank.import")}
        </Button>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {preview && (
        <Card className="space-y-2 p-3">
          <p className="text-sm font-medium text-foreground">{preview.summary}</p>
          {/* diff 是后端给的 Markdown 表格文本：原样等宽展示，不做二次解析——
              解析错了比显示得丑危险得多（用户据此决定要不要落盘） */}
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-surface-0 p-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
            {preview.diff.join("\n")}
          </pre>
          <div className="flex gap-2">
            <Button size="sm" onClick={onConfirmImport} disabled={importing}>
              {t("bank.confirmImport")}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setPreview(null)}>
              {t("common.cancel")}
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <Card className="border-dashed">
          <EmptyState
            icon={<BookOpen size={20} />}
            title={keyword || status ? t("bank.emptyNoMatch") : t("bank.emptyNoData")}
            description={
              keyword || status ? t("bank.emptyHintNoMatch") : t("bank.emptyHintNoData")
            }
          />
        </Card>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">{t("bank.count", { count: total })}</p>
          <div className="space-y-2">
            {rows.map((row) => (
              <QuestionBankRow
                key={row.题目id || row.题目}
                row={row}
                onOpen={() => setSelected(row)}
              />
            ))}
          </div>
        </>
      )}

      {/* 详情（编辑）弹窗：确认写入后关窗并重载，让列表里的徽章同步 */}
      {selected && (
        <QuestionDetailDialog
          item={selected}
          onClose={() => setSelected(null)}
          onSaved={() => {
            setSelected(null);
            load();
          }}
        />
      )}
    </div>
  );
}

export default function QuestionBank() {
  const { t } = useTranslation();
  // 双视图：题库是"要准备的题"，被问过的是"发生过的事实"——两件事，不混在一张表里
  const [view, setView] = useState<"bank" | "asked">("bank");

  const tabs = useMemo(
    () => [
      { key: "bank" as const, label: t("bank.tabMyBank") },
      { key: "asked" as const, label: t("bank.tabAsked") },
    ],
    [t]
  );

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="inline-flex rounded-lg border border-border bg-surface-1 p-0.5">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setView(tab.key)}
            className={
              view === tab.key
                ? "rounded-md bg-primary/10 px-3 py-1 text-xs font-medium text-primary"
                : "px-3 py-1 text-xs text-muted-foreground hover:text-foreground"
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {view === "bank" ? <MyBank /> : <AskedBefore />}
    </div>
  );
}
