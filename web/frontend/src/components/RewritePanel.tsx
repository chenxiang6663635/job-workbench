import { useMemo, useState } from "react";
import { Loader2, ShieldAlert, Sparkles, X } from "lucide-react";
import { api, type SuggestResult } from "../api";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { ErrorBanner } from "./ErrorBanner";
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
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
      setError(t("rewrite.instructionRequired"));
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
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="max-h-[90vh] w-full max-w-3xl overflow-y-auto">
        {/* Dialog 自带 focus trap / Esc / aria-modal——此前手写遮罩都没有 */}
        <DialogHeader>
          <div className="flex items-start justify-between">
            <div>
              <DialogTitle className="flex items-center gap-2">
                <Sparkles size={16} className="text-primary" /> {t("rewrite.title")}
              </DialogTitle>
              <DialogDescription className="mt-0.5">
                {t("rewrite.desc")}
              </DialogDescription>
            </div>
            <DialogClose asChild>
              <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
                <X size={16} />
              </Button>
            </DialogClose>
          </div>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-[1fr_180px]">
          <Input
            placeholder={t("rewrite.phInstruction")}
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <Input
            placeholder={t("rewrite.phModel")}
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </div>
        <Button onClick={generate} disabled={loading} className="mt-3">
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
          {loading ? t("rewrite.generating") : t("rewrite.generate")}
        </Button>

        {error && (
          <ErrorBanner message={error} className="mt-4" />
        )}

        {result && (
          <div className="mt-4 space-y-3">
            {/* 校验结果：通过=绿；未通过=红且列原因，绝不静默 */}
            <div
              className={`flex items-start gap-2 rounded-xl border px-4 py-3 ${
                result.ok
                  ? "border-success/30 bg-success/10"
                  : "border-destructive/40 bg-destructive/10"
              }`}
            >
              <ShieldAlert
                size={15}
                className={`mt-0.5 shrink-0 ${result.ok ? "text-success" : "text-destructive"}`}
              />
              <div className="text-xs">
                {result.ok ? (
                  <p className="text-success">{t("rewrite.checkPassed")}</p>
                ) : (
                  <>
                    <p className="font-medium text-destructive">{t("rewrite.checkFailed")}</p>
                    <ul className="mt-1 list-disc space-y-0.5 pl-4 text-foreground">
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
              <p className="text-xs text-muted-foreground">{t("rewrite.noDiff")}</p>
            ) : (
              <div className="space-y-2">
                {diffs.map((d, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-border bg-background/60 p-3 text-xs"
                  >
                    <p className="mb-1 font-mono text-[10px] text-muted-foreground/70">{d.path}</p>
                    <p className="leading-relaxed text-muted-foreground line-through decoration-destructive/60">
                      {d.oldText || t("app.emptyValue")}
                    </p>
                    <p className="mt-1 leading-relaxed text-foreground">{d.newText}</p>
                  </div>
                ))}
              </div>
            )}

            <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
              {!result.ok ? (
                <Label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    checked={forceAck}
                    onChange={(e) => setForceAck(e.target.checked)}
                    className="cursor-pointer accent-warning"
                  />
                  {t("rewrite.forceAck")}
                </Label>
              ) : (
                <span className="text-xs text-muted-foreground">
                  {t("rewrite.applyNote", { save: t("common.save") })}
                </span>
              )}
              <div className="flex gap-2">
                <DialogClose asChild>
                  <Button variant="outline">{t("common.closeAction")}</Button>
                </DialogClose>
                <Button
                  onClick={() => onApply(result.suggestion)}
                  disabled={!canApply || diffs.length === 0}
                  title={
                    !result.ok && !forceAck ? t("rewrite.blockedTitle") : undefined
                  }
                >
                  {t("rewrite.apply")}
                </Button>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
