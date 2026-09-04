import { useEffect, useState } from "react";
import { Plus, Scale } from "lucide-react";
import { api, type Offer } from "../api";
import OfferForm from "./OfferForm";

// 并排对比的字段清单：逐行对齐，方便扫读。只列事实字段，
// 绝不加「综合评价」之类的判断列——这是产品的伦理边界。
const FIELDS: { key: keyof Offer; label: string }[] = [
  { key: "岗位", label: "岗位" },
  { key: "月薪", label: "月薪" },
  { key: "年终", label: "年终" },
  { key: "签字费", label: "签字费" },
  { key: "股票期权", label: "股票期权" },
  { key: "工作地点", label: "工作地点" },
  { key: "答复截止日", label: "答复截止日" },
  { key: "其他条件", label: "其他条件" },
];

// 答复截止日临近（3 天内）用琥珀提示，但不排序不打分
function deadlineSoon(date: string): boolean {
  if (!date) return false;
  const diff = new Date(date).getTime() - Date.now();
  return diff > 0 && diff < 3 * 86400_000;
}

export default function OfferCompare() {
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

  if (loaded && rows.length === 0) {
    return (
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-8 text-center">
          <Scale size={28} className="mx-auto mb-3 text-slate-600" />
          <p className="text-sm text-slate-400">还没有 Offer 记录</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-600">
            拿到 offer 后把已知事实录进来，多个 offer 会并排在这里——
            <br />
            数字放在一张表里，选择依然是你自己的
          </p>
          <button
            onClick={() => setShowForm(true)}
            className="mt-4 cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-4 py-2 text-xs font-medium text-white transition-all hover:opacity-90"
          >
            录入第一个 Offer
          </button>
        </div>
        {showForm && (
          <OfferForm
            onClose={() => setShowForm(false)}
            onSaved={() => {
              setShowForm(false);
              reload();
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {rows.length} 个 offer · 按答复截止日排列（越先要答复的越靠左）
        </p>
        <button
          onClick={() => setShowForm(true)}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-gradient-to-r from-accent to-accent-dim px-3.5 py-2 text-xs font-medium text-white transition-all hover:opacity-90"
        >
          <Plus size={14} /> 录入 Offer
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-xs text-bad">
          {error}
        </div>
      )}

      {/* 横向并排：字段逐行对齐。offer 多时横向滚动，保持逐行可比 */}
      <div className="overflow-x-auto pb-2">
        <div className="flex gap-4" style={{ minWidth: "min-content" }}>
          {rows.map((o) => (
            <div
              key={o.offer_id}
              className="w-64 shrink-0 rounded-2xl border border-white/10 bg-ink-900/60 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-white/20"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-semibold text-white">{o.公司}</p>
                <span className="rounded-md border border-white/10 bg-ink-950/60 px-1.5 py-0.5 text-[10px] text-slate-500">
                  {o.offer_id}
                </span>
              </div>

              <div className="mt-3 space-y-2">
                {FIELDS.map((f) => {
                  const value = (o[f.key] ?? "").toString();
                  const soon = f.key === "答复截止日" && deadlineSoon(value);
                  return (
                    <div key={f.key} className="flex items-start justify-between gap-2 text-xs">
                      <span className="shrink-0 text-slate-500">{f.label}</span>
                      <span
                        className={`text-right ${
                          soon ? "font-medium text-warn" : "text-slate-200"
                        }`}
                      >
                        {value || <span className="text-slate-600">—</span>}
                      </span>
                    </div>
                  );
                })}
              </div>

              {(o.薪资构成 || o.备注 || o.关联记录) && (
                <div className="mt-3 space-y-1.5 border-t border-white/5 pt-2.5 text-[11px] leading-relaxed text-slate-500">
                  {o.薪资构成 && <p>构成：{o.薪资构成}</p>}
                  {o.备注 && <p>{o.备注}</p>}
                  {o.关联记录 && <p className="text-slate-600">关联 {o.关联记录}</p>}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 固定页脚：产品的伦理边界，永远不替用户做选择 */}
      <p className="rounded-xl border border-white/5 bg-ink-950/40 px-4 py-3 text-center text-xs text-slate-500">
        这里只并排展示你录入的已知事实，最终选择由你决定。
      </p>

      {showForm && (
        <OfferForm
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}
    </div>
  );
}
