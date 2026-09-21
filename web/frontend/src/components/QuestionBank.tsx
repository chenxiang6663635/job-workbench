import { useEffect, useState } from "react";
import { BookOpen, Download, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type BankQuestion } from "../api";
import { AskedBefore } from "./AskedBefore";
import { BankPreviewCard } from "./BankPreviewCard";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { EmptyState } from "./ui/empty";
import { Segmented } from "./ui/segmented";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import { QuestionBankRow } from "./QuestionBankRow";
import { QuestionDetailDialog } from "./QuestionDetailDialog";

const BANK_STATUS = ["未看", "看过", "会了"];

// 「全部状态」在 Radix Select 里不能再用空串（item 的 value 必须非空），用一个
// 不可能与真实状态撞车的哨兵值；出参仍还原成 ""（筛选参数的空值语义不变）。
const ALL_STATUS = "__all__";

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
        <Select
          value={status || ALL_STATUS}
          onValueChange={(value) => setStatus(value === ALL_STATUS ? "" : value)}
        >
          <SelectTrigger className="w-32" aria-label={t("bank.statusFilter")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_STATUS}>{t("bank.allStatus")}</SelectItem>
            {BANK_STATUS.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={onPreviewImport} disabled={importing}>
          <Download size={13} className="mr-1" />
          {importing ? t("bank.importing") : t("bank.import")}
        </Button>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {preview && (
        <BankPreviewCard
          summary={preview.summary}
          diff={preview.diff}
          busy={importing}
          confirmLabel={t("bank.confirmImport")}
          onConfirm={onConfirmImport}
          onCancel={() => setPreview(null)}
        />
      )}

      {/* 三态齐全（与「被问过的」同一套）：失败时只出错误条，不再接着显示
          「题库还是空的」——请求失败与真的没有题是两件事，混报会让人以为数据丢了 */}
      {loading && !error ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      ) : !loading && !error && rows.length === 0 ? (
        <Card className="border-dashed">
          <EmptyState
            icon={<BookOpen size={20} />}
            title={keyword || status ? t("bank.emptyNoMatch") : t("bank.emptyNoData")}
            description={
              keyword || status ? t("bank.emptyHintNoMatch") : t("bank.emptyHintNoData")
            }
          />
        </Card>
      ) : rows.length === 0 ? null : (
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

  return (
    <div className="flex flex-1 flex-col gap-4">
      {/* 双视图切换走 ui/segmented：原生 radio 自带分组语义与方向键，手搓按钮组
          既没有 role 也没有键盘支持（与看板 / 设置页同一套控件） */}
      <Segmented
        value={view}
        onChange={setView}
        ariaLabel={t("bank.viewSwitch")}
        className="self-start"
        options={[
          { value: "bank", label: t("bank.tabMyBank") },
          { value: "asked", label: t("bank.tabAsked") },
        ]}
      />

      {view === "bank" ? <MyBank /> : <AskedBefore />}
    </div>
  );
}
