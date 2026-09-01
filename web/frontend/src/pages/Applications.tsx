import { useEffect, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { api, BATCHES, STAGES, TERMINAL, type Application } from "../api";

const DIRECTIONS = ["datacenter", "hvac", "other"];

function stageStyle(stage: string) {
  if (stage === "已挂") return "bg-bad/15 text-bad";
  if (stage === "已放弃") return "bg-slate-500/15 text-slate-400";
  if (stage === "offer" || stage === "签约")
    return "bg-good/15 text-good";
  return "bg-accent/15 text-accent";
}

export default function Applications() {
  const [items, setItems] = useState<Application[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState({
    stage: "",
    direction: "",
    batch: "",
  });
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState({
    公司: "",
    岗位: "",
    方向: "hvac",
    批次: "正式批",
    评分: 60,
    截止日期: "",
    当前阶段: "待投",
  });

  const load = () => {
    api
      .listApplications(filter)
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, [filter]);

  const patch = (id: string, body: Partial<Application>) => {
    api
      .updateApplication(id, body)
      .then(() => load())
      .catch((e: Error) => setError(e.message));
  };

  const submit = () => {
    // CSV 中评分为字符串，提交前转换
    api
      .addApplication({ ...draft, 评分: String(draft.评分) })
      .then(() => {
        setCreating(false);
        setDraft({
          公司: "",
          岗位: "",
          方向: "hvac",
          批次: "正式批",
          评分: 60,
          截止日期: "",
          当前阶段: "待投",
        });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  const inputCls =
    "w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 text-sm text-slate-100 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/60 focus:ring-1 focus:ring-accent/30";

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-center justify-between rounded-xl border border-bad/30 bg-bad/10 px-4 py-2 text-sm text-bad">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="cursor-pointer">
            <X size={14} />
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-ink-900 px-3">
          <Search size={14} className="text-slate-500" />
          <select
            value={filter.stage}
            onChange={(e) => setFilter({ ...filter, stage: e.target.value })}
            className="cursor-pointer bg-transparent py-2 text-sm text-slate-200 outline-none"
          >
            <option value="">全部阶段</option>
            {STAGES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>

        <select
          value={filter.direction}
          onChange={(e) => setFilter({ ...filter, direction: e.target.value })}
          className="cursor-pointer rounded-lg border border-white/10 bg-ink-900 px-3 py-2 text-sm text-slate-200 outline-none"
        >
          <option value="">全部方向</option>
          {DIRECTIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>

        <select
          value={filter.batch}
          onChange={(e) => setFilter({ ...filter, batch: e.target.value })}
          className="cursor-pointer rounded-lg border border-white/10 bg-ink-900 px-3 py-2 text-sm text-slate-200 outline-none"
        >
          <option value="">全部批次</option>
          {BATCHES.map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>

        <button
          onClick={() => setCreating(true)}
          className="ml-auto flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95"
        >
          <Plus size={16} /> 新增投递
        </button>
      </div>

      {creating && (
        <div className="rounded-2xl border border-accent/30 bg-ink-900/70 p-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <input
              className={inputCls}
              placeholder="公司名称"
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="岗位名称"
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
            <select
              className={inputCls}
              value={draft.方向}
              onChange={(e) => setDraft({ ...draft, 方向: e.target.value })}
            >
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <select
              className={inputCls}
              value={draft.批次}
              onChange={(e) => setDraft({ ...draft, 批次: e.target.value })}
            >
              {BATCHES.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
            <input
              className={inputCls}
              type="date"
              value={draft.截止日期}
              onChange={(e) => setDraft({ ...draft, 截止日期: e.target.value })}
            />
            <input
              className={inputCls}
              type="number"
              min={0}
              max={100}
              value={draft.评分}
              onChange={(e) =>
                setDraft({ ...draft, 评分: Number(e.target.value) })
              }
            />
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={submit}
              disabled={!draft.公司.trim() || !draft.岗位.trim()}
              className="cursor-pointer rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
            >
              保存
            </button>
            <button
              onClick={() => setCreating(false)}
              className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
            >
              取消
            </button>
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
          <p className="text-base font-medium text-slate-200">
            没有匹配的投递记录
          </p>
          <p className="mt-2 text-sm text-slate-400">
            调整筛选条件，或点击右上角「新增投递」记录第一家公司。
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full text-sm">
            <thead className="bg-ink-850 text-xs uppercase tracking-wider text-slate-400">
              <tr>
                <th className="px-4 py-3 text-left font-medium">公司 / 岗位</th>
                <th className="px-4 py-3 text-left font-medium">方向</th>
                <th className="px-4 py-3 text-left font-medium">批次</th>
                <th className="px-4 py-3 text-left font-medium">当前阶段</th>
                <th className="px-4 py-3 text-left font-medium">状态原因</th>
                <th className="px-4 py-3 text-left font-medium">下次动作</th>
                <th className="px-4 py-3 text-left font-medium">截止</th>
                <th className="px-4 py-3 text-left font-medium">评分</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {items.map((it) => (
                <tr
                  key={it.id}
                  className="bg-ink-900/40 transition-colors hover:bg-ink-850"
                >
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">
                      {it.公司 || "—"}
                    </div>
                    <div className="text-xs text-slate-500">
                      {it.岗位 || "未填岗位"}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{it.方向 || "—"}</td>
                  <td className="px-4 py-3 text-slate-300">{it.批次 || "—"}</td>
                  <td className="px-4 py-3">
                    {TERMINAL.includes(it.当前阶段) ? (
                      <div className="flex flex-col gap-0.5">
                        <span
                          className={`rounded-md px-2 py-1 text-xs font-medium ${stageStyle(
                            it.当前阶段
                          )}`}
                        >
                          {it.当前阶段}
                        </span>
                        <span className="text-[10px] text-slate-500">
                          已终态，不可改阶段
                        </span>
                      </div>
                    ) : (
                      <select
                        value={it.当前阶段}
                        onChange={(e) =>
                          patch(it.id, { 当前阶段: e.target.value })
                        }
                        className={`cursor-pointer rounded-md border-0 px-2 py-1 text-xs font-medium outline-none ${stageStyle(
                          it.当前阶段
                        )}`}
                      >
                        {STAGES.map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <input
                      defaultValue={it.状态原因}
                      onBlur={(e) => {
                        if (e.target.value !== it.状态原因) {
                          patch(it.id, { 状态原因: e.target.value });
                        }
                      }}
                      placeholder={
                        TERMINAL.includes(it.当前阶段) ? "必填原因" : "选填"
                      }
                      className="w-full min-w-[8rem] rounded border border-transparent bg-transparent px-2 py-1 text-xs text-slate-200 outline-none transition-colors placeholder:text-slate-600 hover:border-white/10 focus:border-accent/50"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <input
                      defaultValue={it.下次动作}
                      onBlur={(e) => {
                        if (e.target.value !== it.下次动作) {
                          patch(it.id, { 下次动作: e.target.value });
                        }
                      }}
                      placeholder="待补充"
                      className="w-full min-w-[8rem] rounded border border-transparent bg-transparent px-2 py-1 text-xs text-slate-200 outline-none transition-colors placeholder:text-slate-600 hover:border-white/10 focus:border-accent/50"
                    />
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {it.截止日期 || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-accent">
                      {it.评分 || "—"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
