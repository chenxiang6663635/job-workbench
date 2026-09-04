import { useEffect, useState } from "react";
import { GitBranch, LayoutList } from "lucide-react";
import { api, type LineageItem } from "../api";

// 阶段徽章配色：进行中=青蓝、成功=绿、终态=灰
function stageCls(stage: string): string {
  if (stage === "offer" || stage === "签约") return "bg-good/15 text-good border-good/30";
  if (stage === "已挂" || stage === "已放弃") return "bg-white/5 text-slate-500 border-white/10";
  return "bg-accent/10 text-accent border-accent/25";
}

/**
 * 版本谱系：每个简历版本投了哪些岗位、各处于什么阶段。
 * 数据来自 tracker.csv 的「简历版本」列，纯只读聚合——
 * 回答"这版简历到底投给了谁"，派生关系一目了然。
 */
export default function VersionLineage() {
  const [items, setItems] = useState<LineageItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .lineage()
      .then((r) => {
        setItems(r.items);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return null;
  if (loaded && items.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <GitBranch size={15} className="text-accent" />
        <h3 className="text-sm font-medium text-slate-200">版本谱系</h3>
        <span className="text-[11px] text-slate-600">
          每个版本投了哪些岗位、走到哪一步
        </span>
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((it) => (
          <div key={it.version} className="rounded-xl border border-white/10 bg-ink-900/60 p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-slate-100">{it.version}</p>
              <span className="text-[11px] text-slate-500">{it.total} 个岗位</span>
            </div>
            <div className="mt-2.5 space-y-1.5">
              {it.applications.map((a) => (
                <div key={a.id} className="flex items-center gap-2 text-xs">
                  <span className="w-11 shrink-0 text-slate-600">{a.id}</span>
                  <span className="flex-1 truncate text-slate-300">
                    {a.公司} {a.岗位}
                  </span>
                  {a.投递日期 && (
                    <span className="shrink-0 text-slate-600">{a.投递日期}</span>
                  )}
                  <span
                    className={`shrink-0 rounded-md border px-1.5 py-0.5 text-[10px] ${stageCls(a.当前阶段)}`}
                  >
                    {a.当前阶段 || "—"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {loaded && items.some((i) => i.version === "（未填版本）") && (
        <p className="text-[11px] text-slate-600">
          提示：投递时在追踪表里填「简历版本」，谱系才能把版本和岗位连起来。
        </p>
      )}
    </div>
  );
}
