import { useMemo, useState } from "react";
import { Loader2, ShieldAlert, Sparkles, X } from "lucide-react";
import { api, type SuggestResult } from "../api";

const inputCls =
  "w-full rounded-lg border border-white/10 bg-ink-950/60 px-3 py-2 text-sm text-slate-200 outline-none transition-colors placeholder:text-slate-600 focus:border-accent/50";

interface DiffItem {
  path: string;
  oldText: string;
  newText: string;
}

// 递归收集变化的叶子字符串：diff 只看文字改动
function collectDiff(
  orig: unknown,
  sugg: unknown,
  path: string,
  out: DiffItem[]
): void {
  if (typeof orig === "string" || typeof sugg === "string") {
    const o = typeof orig === "string" ? orig : "";
    const n = typeof sugg === "string" ? sugg : "";
    if (o !== n) out.push({ path, oldText: o, newText: n });
    return;
  }
  if (Array.isArray(orig) && Array.isArray(sugg)) {
    orig.forEach((_, i) =>
      collectDiff(orig[i], sugg[i], `${path}[${i}]`, out)
    );
    return;
  }
  if (orig && sugg && typeof orig === "object" && typeof sugg === "object") {
    const oRec = orig as Record<string, unknown>;
    const sRec = sugg as Record<string, unknown>;
    Object.keys(oRec).forEach((k) =>
      collectDiff(oRec[k], sRec[k], path ? `${path}.${k}` : k, out)
    );
  }
}

export default function RewritePanel({
  version,
  original,
  onApply,
  onClose,
}: {
  version: string;
  original: Record<string, unknown>;
  onApply: (suggestion: Record<string, unknown>) => void;
  onClose: () => void;
}) {
  const [instruction, setInstruction] = useState("");
  const [model, setModel] = useState(
    () => localStorage.getItem("jobws_rewrite_model") ?? ""
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SuggestResult | null>(null);
  const [forceAck, setForceAck] = useState(false);

  const diffs = useMemo(() => {
    if (!result) return [];
    const out: DiffItem[] = [];
    collectDiff(original, result.suggestion, "", out);
    return out;
  }, [result, original]);

  const generate = () => {
    if (!instruction.trim()) {
      setError("先写一句改写方向");
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    setForceAck(false);
    if (model.trim()) {
      try {
        localStorage.setItem("jobws_rewrite_model", model.trim());
      } catch {
        // localStorage 不可用不阻塞
      }
    }
    api
      .suggestRewrite(version, { instruction, model: model.trim() })
      .then((r) => {
        setResult(r);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  };

  const canApply = result && (result.ok || forceAck);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-6 backdrop-blur-sm">
      <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl">
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h3 className="flex items-center gap-2 text-base font-semibold text-white">
              <Sparkles size={16} className="text-accent" /> AI 改写建议
            </h3>
            <p className="mt-0.5 text-xs text-slate-500">
              只改写既有事实的表述。建议先过反编造校验，通过才能直接采用
            </p>
          </div>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-white/5 hover:text-slate-200"
          >
            <X size={18} />
          </button>
        </div>

        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <input
            className={inputCls}
            placeholder="改写方向，如：把项目表述往数据中心冷却方向靠"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <input
            className={inputCls}
            placeholder="模型名，如 deepseek-chat"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="mt-3 flex cursor-pointer items-center gap-1.5 rounded-lg bg-gradient-to-r from-accent to-accent-dim px-4 py-2 text-sm font-medium text-white transition-all hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {loading ? "生成中…" : "生成建议"}
        </button>

        {error && (
          <div className="mt-4 rounded-xl border border-bad/30 bg-bad/10 px-4 py-3 text-xs text-bad">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-4 space-y-3">
            {/* 校验结果：通过=绿；未通过=红且列原因，绝不静默 */}
            <div
              className={`flex items-start gap-2 rounded-xl border px-4 py-3 ${
                result.ok
                  ? "border-good/30 bg-good/10"
                  : "border-bad/40 bg-bad/10"
              }`}
            >
              <ShieldAlert
                size={15}
                className={`mt-0.5 shrink-0 ${result.ok ? "text-good" : "text-bad"}`}
              />
              <div className="text-xs">
                {result.ok ? (
                  <p className="text-good">反编造校验通过：无新增数字、结构未动、身份未改</p>
                ) : (
                  <>
                    <p className="font-medium text-bad">校验未通过，默认不可采用：</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-slate-300">
                      {result.issues.map((i, idx) => (
                        <li key={idx}>{i}</li>
                      ))}
                    </ul>
                  </>
                )}
              </div>
            </div>

            {/* diff：逐处改动，原文 → 建议 */}
            {diffs.length === 0 ? (
              <p className="text-xs text-slate-500">模型没有给出任何文字改动。</p>
            ) : (
              <div className="space-y-2">
                {diffs.map((d, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-white/10 bg-ink-950/40 p-3 text-xs"
                  >
                    <p className="mb-1 font-mono text-[10px] text-slate-600">{d.path}</p>
                    <p className="leading-relaxed text-slate-500 line-through decoration-bad/60">
                      {d.oldText || "（空）"}
                    </p>
                    <p className="mt-1 leading-relaxed text-slate-200">{d.newText}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between gap-3 border-t border-white/10 pt-4">
              {!result.ok ? (
                <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400">
                  <input
                    type="checkbox"
                    checked={forceAck}
                    onChange={(e) => setForceAck(e.target.checked)}
                    className="cursor-pointer accent-warn"
                  />
                  我逐条看过上述问题，确认没有编造内容，仍要采用
                </label>
              ) : (
                <span className="text-xs text-slate-500">
                  采用后会覆盖编辑区内容，仍需手动点「保存」落盘
                </span>
              )}
              <div className="flex gap-2">
                <button
                  onClick={onClose}
                  className="cursor-pointer rounded-lg border border-white/10 px-4 py-2 text-sm text-slate-300 transition-colors hover:bg-white/5"
                >
                  关闭
                </button>
                <button
                  onClick={() => onApply(result.suggestion)}
                  disabled={!canApply || diffs.length === 0}
                  title={
                    !result.ok && !forceAck
                      ? "校验未通过，先勾选确认才能采用"
                      : undefined
                  }
                  className="cursor-pointer rounded-lg bg-gradient-to-r from-accent to-accent-dim px-4 py-2 text-sm font-medium text-white transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  采用建议
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
