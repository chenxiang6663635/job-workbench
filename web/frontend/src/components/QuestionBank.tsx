import { useEffect, useRef, useState } from "react";
import { BookOpen, Plus, Search } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api } from "../api";
import type { BankRow } from "../lib/bank";
import { AskedBefore } from "./AskedBefore";
import { BankCounts } from "./BankCounts";
import { BankImportButton } from "./BankImportButton";
import { QuestionForm } from "./QuestionForm";
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
  const [rows, setRows] = useState<BankRow[]>([]);
  const [total, setTotal] = useState(0);
  // 三态计数随列表拉回（B-4）：练到哪了一眼可见
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // 详情（也就是编辑）弹窗：null = 关闭，否则为被打开的那一行
  const [selected, setSelected] = useState<BankRow | null>(null);
  // 「新增题目」弹窗（批次 B-1）：加题入口从 CLI 挪进界面
  const [adding, setAdding] = useState(false);

  // 序号守卫：250ms 防抖只减少请求数，拦不住「改筛选后旧响应后到」——
  // 它 `.finally` 里的 setLoading(false) 还会把正在进行的那一次提前解锁
  const loadSeq = useRef(0);
  const load = () => {
    const seq = ++loadSeq.current;
    setLoading(true);
    setError(null);
    api
      .bankQuestions({ q: keyword.trim() || undefined, status: status || undefined })
      .then(
        (r) => {
          if (seq !== loadSeq.current) return;
          setRows(r.items);
          setTotal(r.total);
          setCounts(r.counts);
        },
        (e: Error) => {
          if (seq === loadSeq.current) setError(e.message);
        }
      )
      .then(() => {
        if (seq === loadSeq.current) setLoading(false);
      });
  };

  // 防抖：关键词每敲一下就打接口不划算；筛选变化则立即重载
  useEffect(() => {
    const timer = setTimeout(load, 250);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [keyword, status]);

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
        {/* 导入的路整体抽到 BankImportButton（含预览 → 确认的两段式） */}
        <BankImportButton onImported={load} />
        <Button size="sm" onClick={() => setAdding(true)}>
          <Plus size={13} className="mr-1" />
          {t("bank.addQuestion")}
        </Button>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

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
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-xs text-muted-foreground">{t("bank.count", { count: total })}</p>
            {/* 三态分布（B-4）：counts 后端早就算好了，此前前端零消费 */}
            <BankCounts counts={counts} />
          </div>
          <div className="space-y-2">
            {rows.map((row, index) => {
              // 无 id 且题名重复的行（CSV 手改场景）会撞 key——补 index 后缀保证唯一
              // （审查 n6；变量拼接而非模板串：`||` 会被 i18n 豁免清单的 `|` 分隔符拆坏）
              const rowKey = [row.题目id, row.题目, index].join("|");
              return (
                <QuestionBankRow key={rowKey} row={row} onOpen={() => setSelected(row)} />
              );
            })}
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

      {/* 新增题目（批次 B-1）：确认落盘后关窗并重载 */}
      {adding && (
        <QuestionForm
          onClose={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
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
