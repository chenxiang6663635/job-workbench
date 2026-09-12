import { useState } from "react";
import { ArrowRight, CheckCircle2, Loader2, Mail, X } from "lucide-react";
import {
  api,
  STAGES,
  TERMINAL,
  type Application,
  type StatusMatch,
  type StatusSuggestResult,
} from "../api";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  applications: Application[];
  onClose: () => void;
  onApplied: () => void;
}

const NONE = "__none__";

/**
 * 粘贴原文 → 解析出建议 → 逐条确认写回（B11）。
 *
 * 复用批量导入的两阶段思路：解析只读、确认才写。差别在于这里更**不允许猜**：
 * 没认出阶段就让用户选，匹配不上就让用户指定记录——宁可多一步，也不要把
 * 一封邮件错误地写进另一条记录。服务端还会在锁内重算一遍规则（见
 * `apply-status-suggestion`），这里的所有勾选只是意图，不是权限。
 */
export default function StatusUpdateDialog({ applications, onClose, onApplied }: Props) {
  const [text, setText] = useState("");
  const [manualId, setManualId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<StatusSuggestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failures, setFailures] = useState<string[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [stageOverride, setStageOverride] = useState<Record<string, string>>({});

  const stageOf = (m: StatusMatch) => stageOverride[m.id] || m.建议阶段;

  const run = () => {
    if (!text.trim()) {
      setError("请先粘贴邮件或站内信原文");
      return;
    }
    setBusy(true);
    setError(null);
    setFailures([]);
    api
      .suggestStatus(text, manualId || undefined)
      .then((r) => {
        setResult(r);
        // 默认勾上「规则允许改 + 认出了阶段」的那些；其余留给用户显式选择
        const nextPicked: Record<string, boolean> = {};
        const nextReasons: Record<string, string> = {};
        r.matches.forEach((m) => {
          nextPicked[m.id] = m.可覆盖 && !!m.建议阶段;
          // 终态必填原因：把命中的原句作为默认值——用户通常只需删改一下
          if (TERMINAL.includes(m.建议阶段)) nextReasons[m.id] = m.证据.join("；");
        });
        setPicked(nextPicked);
        setReasons(nextReasons);
        setStageOverride({});
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const apply = async () => {
    if (!result) return;
    const targets = result.matches.filter((m) => picked[m.id]);
    if (targets.length === 0) {
      setError("请先勾选要应用的记录");
      return;
    }
    const missingReason = targets.find(
      (m) => TERMINAL.includes(stageOf(m)) && !(reasons[m.id] || "").trim()
    );
    if (missingReason) {
      setError(`进入终态必须填写原因：${missingReason.公司} ${missingReason.岗位}`);
      return;
    }

    setBusy(true);
    setError(null);
    setFailures([]);
    const failed: string[] = [];
    for (const m of targets) {
      try {
        await api.applyStatusSuggestion({
          id: m.id,
          阶段: stageOf(m),
          // 原样回传用户看到的当前阶段：服务端据此判断这条建议是否已过期
          原阶段: m.当前阶段,
          状态原因: reasons[m.id] || undefined,
          依据: m.证据.join("；") || undefined,
        });
      } catch (e) {
        failed.push(`${m.公司} ${m.岗位}：${(e as Error).message}`);
      }
    }
    setBusy(false);
    onApplied();
    if (failed.length === 0) {
      onClose();
    } else {
      // 部分成功也刷新（成功的已经落盘了），把失败的留在屏幕上说明原因
      setFailures(failed);
    }
  };

  const pickedCount = result
    ? result.matches.filter((m) => picked[m.id]).length
    : 0;

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[88vh] w-full max-w-4xl flex-col gap-0 rounded-2xl p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Mail size={16} className="text-primary" /> 粘贴邮件更新投递状态
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <DialogDescription className="text-sm">
            把笔试 / 面试 / offer / 拒信的原文整段粘进来，解析出「改哪条、改成什么、
            依据哪句话」。<span className="text-muted-foreground">
              解析不会改动任何数据，只有你逐条确认后才会写入，并记入变更时间线。
            </span>
          </DialogDescription>

          <Textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setResult(null);
            }}
            rows={7}
            spellCheck={false}
            placeholder="例如：您好！感谢您投递某某科技热管理工程师岗位，现邀请您参加第二轮面试，面试时间 9月25日 14:00……"
            className="resize-y text-[13px]"
          />

          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={manualId || NONE}
              onValueChange={(v) => setManualId(v === NONE ? "" : v)}
            >
              <SelectTrigger className="w-72">
                <SelectValue placeholder="指定记录（可选）" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>自动识别（按原文里的公司名）</SelectItem>
                {applications.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.公司} {a.岗位}（{a.当前阶段}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">
              站内信经常通篇不写公司名，这时在这条记录上手选一次
            </span>
            <Button onClick={run} disabled={busy} className="ml-auto">
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              解析原文
            </Button>
          </div>

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {failures.length > 0 && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <p className="mb-1 font-medium">以下记录没能写入（其余已成功）：</p>
              <ul className="list-disc space-y-0.5 pl-4">
                {failures.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          {result && <SuggestionReport result={result} picked={picked} reasons={reasons}
                                       stageOverride={stageOverride}
                                       onToggle={(id, v) => setPicked({ ...picked, [id]: v })}
                                       onReason={(id, v) => setReasons({ ...reasons, [id]: v })}
                                       onStage={(id, v) => setStageOverride({ ...stageOverride, [id]: v })} />}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {result
              ? pickedCount > 0
                ? `将更新 ${pickedCount} 条记录，并逐条记入变更时间线`
                : "勾选要应用的记录后才会写入"
              : "先解析原文，确认建议后再写入"}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              取消
            </Button>
            <Button onClick={apply} disabled={!result || pickedCount === 0 || busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              应用更新
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------

interface ReportProps {
  result: StatusSuggestResult;
  picked: Record<string, boolean>;
  reasons: Record<string, string>;
  stageOverride: Record<string, string>;
  onToggle: (id: string, v: boolean) => void;
  onReason: (id: string, v: string) => void;
  onStage: (id: string, v: string) => void;
}

function SuggestionReport({
  result,
  picked,
  reasons,
  stageOverride,
  onToggle,
  onReason,
  onStage,
}: ReportProps) {
  if (result.matches.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        没有匹配到追踪表里的记录。请在上方「指定记录」里选一条后重新解析。
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {result.ambiguous && (
        <p className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-xs text-warning">
          原文里既有拒信措辞又有 offer 措辞，无法判断方向——已不给出阶段建议，请人工核对。
        </p>
      )}
      {result.notes.map((n, i) => (
        <p key={i} className="text-xs text-muted-foreground">
          {n}
        </p>
      ))}
      {result.matches.map((m) => (
        <MatchCard
          key={m.id}
          match={m}
          picked={!!picked[m.id]}
          reason={reasons[m.id] || ""}
          stage={stageOverride[m.id] || m.建议阶段}
          onToggle={(v) => onToggle(m.id, v)}
          onReason={(v) => onReason(m.id, v)}
          onStage={(v) => onStage(m.id, v)}
        />
      ))}
    </div>
  );
}

function MatchCard({
  match,
  picked,
  reason,
  stage,
  onToggle,
  onReason,
  onStage,
}: {
  match: StatusMatch;
  picked: boolean;
  reason: string;
  stage: string;
  onToggle: (v: boolean) => void;
  onReason: (v: string) => void;
  onStage: (v: string) => void;
}) {
  const needsStage = !match.建议阶段;
  const terminal = TERMINAL.includes(stage);
  const blocked = !match.可覆盖;
  return (
    <div className="rounded-xl border border-border bg-card/60 p-3 shadow-sm">
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          className="mt-1 h-4 w-4 accent-primary"
          checked={picked}
          disabled={blocked || needsStage}
          onChange={(e) => onToggle(e.target.checked)}
          title={blocked ? match.原因 : needsStage ? "请先选择要改成的阶段" : ""}
        />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm">
            <span className="font-medium text-foreground">
              {match.公司} {match.岗位}
            </span>
            <span className="text-xs text-muted-foreground">{match.id} · {match.命中}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded bg-secondary/60 px-2 py-0.5 text-xs text-muted-foreground">
              {match.当前阶段 || "—"}
            </span>
            <ArrowRight size={14} className="text-primary" />
            {/* 建议阶段直接做成可改的下拉：一处控件既展示建议也允许改。
                分成「徽章显示建议 + 另一处选择改成什么」迟早会对不上。 */}
            <Select value={stage || undefined} onValueChange={onStage}>
              <SelectTrigger className="h-8 w-36 text-xs">
                <SelectValue placeholder="选择阶段" />
              </SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {!needsStage && (
              <span className="text-xs text-muted-foreground">（规则建议，可改）</span>
            )}
          </div>

          {match.证据.length > 0 && (
            <p className="border-l-2 border-primary/30 pl-2 text-xs italic text-muted-foreground">
              「{match.证据.join("」「")}」
            </p>
          )}

          {blocked && (
            <p className="text-xs text-warning">{match.原因}</p>
          )}

          {terminal && (
            <div className="flex items-center gap-2">
              <span className="shrink-0 text-xs text-muted-foreground">状态原因</span>
              <Input
                value={reason}
                onChange={(e) => onReason(e.target.value)}
                placeholder="进入终态必须填写（默认填入命中的原句，可改）"
                className="h-8 text-xs"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
