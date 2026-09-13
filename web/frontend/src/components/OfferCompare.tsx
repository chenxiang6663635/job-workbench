import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Scale } from "lucide-react";
import { api, type Offer } from "../api";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import OfferForm from "./OfferForm";

// 并排对比的字段清单：逐行对齐，方便扫读。只列事实字段，
// 绝不加「综合评价」之类的判断列——这是产品的伦理边界。
//
// key 是 offer CSV 的真实列名（不翻译，取值全靠它）；label 表头是展示文案，
// 所以这里存的是翻译 key 而不是字面量——表在组件外定义，拿不到当时的 t()。
const FIELDS: { key: keyof Offer; labelKey: TranslationKey }[] = [
  { key: "岗位", labelKey: "offer.field.role" },
  { key: "月薪", labelKey: "offer.field.monthly" },
  { key: "年终", labelKey: "offer.field.bonus" },
  { key: "签字费", labelKey: "offer.field.signOn" },
  { key: "股票期权", labelKey: "offer.field.equity" },
  { key: "工作地点", labelKey: "offer.field.location" },
  { key: "答复截止日", labelKey: "offer.field.deadline" },
  { key: "其他条件", labelKey: "offer.field.other" },
];

// 答复截止日临近（3 天内）用琥珀提示，但不排序不打分
function deadlineSoon(date: string): boolean {
  if (!date) return false;
  const diff = new Date(date).getTime() - Date.now();
  return diff > 0 && diff < 3 * 86400_000;
}

export default function OfferCompare() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Offer[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const reload = () => {
    api
      .listOffers()
      .then((r) => {
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(reload, []);

  const form = showForm && (
    <OfferForm
      onClose={() => setShowForm(false)}
      onSaved={() => {
        setShowForm(false);
        reload();
      }}
    />
  );

  // 三态齐全：loading 骨架 / empty 空态 / error 错误条
  if (!loaded) {
    return (
      <div className="space-y-4">
        {error ? (
          <ErrorBanner message={error} onClose={() => setError(null)} />
        ) : (
          <div className="flex gap-4">
            {[0, 1].map((i) => (
              <Skeleton key={i} className="h-64 w-64 shrink-0 rounded-2xl" />
            ))}
          </div>
        )}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="space-y-4">
        <Card className="flex flex-col items-center border-dashed p-8 text-center">
          <Scale size={28} className="mb-3 text-muted-foreground/70" />
          <p className="text-sm text-muted-foreground">{t("offer.emptyTitle")}</p>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground/70">
            {t("offer.emptyHint1")}
            <br />
            {t("offer.emptyHint2")}
          </p>
          <Button className="mt-4" onClick={() => setShowForm(true)}>
            {t("offer.emptyCta")}
          </Button>
        </Card>
        {form}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {t("offer.summary", { count: rows.length })}
        </p>
        <Button onClick={() => setShowForm(true)}>
          <Plus size={14} /> {t("offer.add")}
        </Button>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 横向并排：字段逐行对齐。offer 多时横向滚动，保持逐行可比 */}
      <div className="overflow-x-auto pb-2">
        <div className="flex gap-4" style={{ minWidth: "min-content" }}>
          {rows.map((o) => (
            <Card
              key={o.offer_id}
              className="w-64 shrink-0 rounded-2xl p-4 hover:-translate-y-0.5 hover:border-primary/30"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold text-foreground">{o.公司}</p>
                <Badge variant="outline" className="rounded-md px-1.5 py-0 font-mono text-[10px]">
                  {o.offer_id}
                </Badge>
              </div>

              <div className="mt-3 space-y-2">
                {FIELDS.map((f) => {
                  const value = (o[f.key] ?? "").toString();
                  const soon = f.key === "答复截止日" && deadlineSoon(value);
                  return (
                    <div key={f.key} className="flex items-start justify-between gap-2 text-xs">
                      <span className="shrink-0 text-muted-foreground">{t(f.labelKey)}</span>
                      <span
                        className={`text-right ${soon ? "font-medium text-warning" : "text-foreground"}`}
                      >
                        {value || <span className="text-muted-foreground/70">—</span>}
                      </span>
                    </div>
                  );
                })}
              </div>

              {(o.薪资构成 || o.备注 || o.关联记录) && (
                <div className="mt-3 space-y-1.5 border-t border-border pt-2.5 text-[11px] leading-relaxed text-muted-foreground">
                  {o.薪资构成 && <p>{t("offer.composition", { value: o.薪资构成 })}</p>}
                  {o.备注 && <p>{o.备注}</p>}
                  {o.关联记录 && (
                    <p className="text-muted-foreground/70">{t("offer.related", { value: o.关联记录 })}</p>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      </div>

      {/* 固定页脚：产品的伦理边界，永远不替用户做选择 */}
      <p className="rounded-xl border border-border bg-background/60 px-4 py-3 text-center text-xs text-muted-foreground">
        {t("offer.disclaimer")}
      </p>

      {form}
    </div>
  );
}
