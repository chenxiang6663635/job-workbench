import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowRight, CheckCircle2, Loader2, Mail, Plus, X } from "lucide-react";
import {
  api,
  BATCHES,
  DIRECTIONS,
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
  /** 预填原文（如从 IMAP 拉取的邮件正文）；用户仍可编辑后再解析 */
  initialText?: string;
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
export default function StatusUpdateDialog({ applications, onClose, onApplied, initialText }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState(initialText ?? "");
  const [manualId, setManualId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<StatusSuggestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failures, setFailures] = useState<string[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [stageOverride, setStageOverride] = useState<Record<string, string>>({});
  const [createdNotice, setCreatedNotice] = useState<string | null>(null);

  const stageOf = (m: StatusMatch) => stageOverride[m.id] || m.建议阶段;

  const run = () => {
    if (!text.trim()) {
      setError(t("status.pasteRequired"));
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
      setError(t("status.pickRequired"));
      return;
    }
    const missingReason = targets.find(
      (m) => TERMINAL.includes(stageOf(m)) && !(reasons[m.id] || "").trim()
    );
    if (missingReason) {
      setError(
        t("status.reasonRequired", { label: `${missingReason.公司} ${missingReason.岗位}` })
      );
      return;
    }

    setBusy(true);
    setError(null);
    setFailures([]);
    const failed: string[] = [];
    const done: string[] = [];
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
        done.push(m.id);
      } catch (e) {
        failed.push(
          t("status.applyFailed", { label: `${m.公司} ${m.岗位}`, error: (e as Error).message })
        );
      }
    }
    setBusy(false);
    onApplied();
    if (failed.length === 0) {
      onClose();
      return;
    }
    // 写成功的从勾选里摘掉：否则用户再点一次「应用更新」会对**已经写回**的记录
    // 重发请求——那时它的原阶段早变了，必然 409，失败列表会从「1 条」涨成「全部」，
    // 用户就再也收敛不到成功。
    setPicked((prev) => {
      const next = { ...prev };
      done.forEach((id) => {
        next[id] = false;
      });
      return next;
    });
    setFailures(failed);
  };

  const pickedCount = result
    ? result.matches.filter((m) => picked[m.id]).length
    : 0;

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[88vh] w-full max-w-4xl flex-col gap-0 rounded-2xl p-0">
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <Mail size={16} className="text-primary" /> {t("status.title")}
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        <div className="flex-1 space-y-4 overflow-y-auto p-5">
          <DialogDescription className="text-sm">
            {t("status.desc")}
            <span className="text-muted-foreground"> {t("status.descNote")}</span>
          </DialogDescription>

          <Textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setResult(null);
            }}
            rows={7}
            spellCheck={false}
            placeholder={t("status.placeholder")}
            className="resize-y text-[13px]"
          />

          <div className="flex flex-wrap items-center gap-3">
            <Select
              value={manualId || NONE}
              onValueChange={(v) => setManualId(v === NONE ? "" : v)}
            >
              <SelectTrigger className="w-72">
                <SelectValue placeholder={t("status.pickRecord")} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NONE}>{t("status.autoMatch")}</SelectItem>
                {applications.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.公司} {a.岗位}（{a.当前阶段}）
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">
              {t("status.manualHint")}
            </span>
            <Button onClick={run} disabled={busy} className="ml-auto">
              {busy ? <Loader2 size={14} className="animate-spin" /> : null}
              {t("status.parse")}
            </Button>
          </div>

          {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

          {createdNotice && (
            <p className="rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-xs text-muted-foreground">
              {createdNotice}
            </p>
          )}

          {failures.length > 0 && (
            <div className="rounded-xl border border-destructive/40 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <p className="mb-1 font-medium">{t("status.failedHeader")}</p>
              <ul className="list-disc space-y-0.5 pl-4">
                {failures.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}

          {/* 没有匹配到记录时，直接给「新建记录」的出口——邮件来了而追踪表里
              还没有这条投递，是最常见的断点（投递确认类邮件尤其如此） */}
          {result && result.matches.length === 0 && (
            <NewRecordPanel
              result={result}
              onCreated={(id, label, stage) => {
                setManualId(id);
                setCreatedNotice(t("status.createdNotice", { label, stage }));
                onApplied();
              }}
            />
          )}

          {result && result.matches.length > 0 && (
            <SuggestionReport result={result} picked={picked} reasons={reasons}
                                       stageOverride={stageOverride}
                                       onToggle={(id, v) => setPicked({ ...picked, [id]: v })}
                                       onReason={(id, v) => setReasons({ ...reasons, [id]: v })}
                                       onStage={(id, v) => setStageOverride({ ...stageOverride, [id]: v })} />
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {failures.length > 0
              ? t("status.footerPartial")
              : result
                ? pickedCount > 0
                  ? t("status.footerPicked", { count: pickedCount })
                  : t("status.footerNeedPick")
                : t("status.footerNeedParse")}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={apply} disabled={!result || pickedCount === 0 || busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <CheckCircle2 size={14} />}
              {t("status.apply")}
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
  const { t } = useTranslation();
  if (result.matches.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        {t("status.noMatchHint")}
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {result.ambiguous && (
        <p className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-xs text-warning">
          {t("status.ambiguous")}
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

// ---------------------------------------------------------------------------

interface NewRecordPanelProps {
  result: StatusSuggestResult;
  onCreated: (id: string, label: string, stage: string) => void;
}

/**
 * 「查无记录 → 一键新建」：邮件属于尚未记录的投递时的出口。
 *
 * 当前阶段默认取邮件信号（投递确认 → 已投；面试邀请 → 一面…），可改——
 * 信号只是建议，建什么记录由用户定。方向与批次创建后不可改（服务端同一条
 * 约束），所以在这里显式选择，而不是替用户猜一个。
 */
function NewRecordPanel({ result, onCreated }: NewRecordPanelProps) {
  const { t } = useTranslation();
  const signalStage =
    result.signals.length > 0 && result.signals[0].stage
      ? result.signals[0].stage
      : "已投";
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [direction, setDirection] = useState("other");
  const [batch, setBatch] = useState("正式批");
  const [stage, setStage] = useState(signalStage);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const create = () => {
    if (!company.trim() || !role.trim()) {
      setErr(t("form.companyRoleRequired"));
      return;
    }
    setBusy(true);
    setErr(null);
    api
      .addApplication({
        公司: company.trim(),
        岗位: role.trim(),
        方向: direction,
        批次: batch,
        当前阶段: stage,
      })
      .then((r) => {
        setDone(true);
        onCreated(r.item.id, `${r.item.公司} ${r.item.岗位}`, stage);
      })
      .catch((e: Error) => setErr(e.message))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-3 rounded-xl border border-dashed border-border p-4">
      <p className="text-sm text-muted-foreground">
        {t("status.newRecordHint")}
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Input
          placeholder={t("form.companyRequired")}
          value={company}
          disabled={done}
          onChange={(e) => setCompany(e.target.value)}
          className="h-8 text-xs"
        />
        <Input
          placeholder={t("form.roleRequired")}
          value={role}
          disabled={done}
          onChange={(e) => setRole(e.target.value)}
          className="h-8 text-xs"
        />
        <Select value={direction} onValueChange={setDirection} disabled={done}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DIRECTIONS.map((d) => (
              <SelectItem key={d} value={d}>
                {d}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={batch} onValueChange={setBatch} disabled={done}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BATCHES.map((b) => (
              <SelectItem key={b} value={b}>
                {b}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={stage} onValueChange={setStage} disabled={done}>
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STAGES.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {err && <p className="text-xs text-destructive">{err}</p>}
      <div className="flex flex-wrap items-center gap-3">
        <Button className="h-8 px-3 text-xs" onClick={create} disabled={busy || done}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
          {done ? t("status.created") : t("status.create")}
        </Button>
        <span className="text-xs text-muted-foreground">
          {t("status.newRecordNote", { stage: signalStage })}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

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
  const { t } = useTranslation();
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
          title={blocked ? match.原因 : needsStage ? t("status.pickStageFirst") : ""}
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
                <SelectValue placeholder={t("form.selectStage")} />
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
              <span className="text-xs text-muted-foreground">{t("status.ruleSuggestion")}</span>
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
              <span className="shrink-0 text-xs text-muted-foreground">{t("status.reasonLabel")}</span>
              <Input
                value={reason}
                onChange={(e) => onReason(e.target.value)}
                placeholder={t("status.reasonPlaceholder")}
                className="h-8 text-xs"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
