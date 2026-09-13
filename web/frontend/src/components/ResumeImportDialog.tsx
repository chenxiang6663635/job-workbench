import { useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import { FileUp, Loader2, ShieldCheck, X } from "lucide-react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input, Textarea } from "./ui/input";
import { Label } from "./ui/label";
import { ErrorBanner } from "./ErrorBanner";
import { api, type ImportResult } from "../api";

const ALLOWED = [".pdf", ".docx", ".md", ".markdown", ".txt"];
const MAX_MB = 10;

interface Props {
  currentVersion: string;
  onClose: () => void;
  onImported: (version: string) => void;
}

// 关键字段（诚实红线：这些字段若被模型补全危害最大，单独输入框 + 红/黄描边）
// 只有 label 翻。**`amber` 是数据不是文案**：它拿去和后端返回的 `unfilled`
// （中文键名）做匹配，翻了就永远匹配不上，待补填的高亮会静默失效
const BASICS_KEYS: { key: string; labelKey: TranslationKey; amber: string }[] = [
  { key: "name", labelKey: "resumeImp.fieldName", amber: "姓名" },
  { key: "phone", labelKey: "resumeImp.fieldPhone", amber: "电话" },
  { key: "email", labelKey: "resumeImp.fieldEmail", amber: "邮箱" },
  { key: "location", labelKey: "resumeImp.fieldLocation", amber: "" },
];

// 模块级函数拿不到 t()，所以失败文案由调用方传入（而不是在这里写死任何语言）
function toBase64(file: File, readFailedMsg: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve((r.result as string).split(",")[1] || "");
    r.onerror = () => reject(new Error(readFailedMsg));
    r.readAsDataURL(file);
  });
}

export default function ResumeImportDialog({ currentVersion, onClose, onImported }: Props) {
  const { t } = useTranslation();
  const [model, setModel] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [basics, setBasics] = useState<Record<string, string>>({});
  const [restJson, setRestJson] = useState("");
  const [ack, setAck] = useState(false);
  const [target, setTarget] = useState(currentVersion || "import");
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  // useMemo 包一层：裸的 `|| []` 每次渲染都造新数组，下方 useMemo([issues])
  // 的依赖会随之每次变化（CI 的 react-hooks 警告即此）
  const issues = useMemo(() => result?.issues || [], [result]);
  const unfilled = result?.unfilled || [];
  const basicsRed = useMemo(
    () => (k: string) => issues.some((i) => i.startsWith(`basics.${k}`)),
    [issues]
  );
  const restOk = useMemo(() => {
    try {
      const v = JSON.parse(restJson);
      return v && typeof v === "object" && !Array.isArray(v);
    } catch {
      return false;
    }
  }, [restJson]);

  const pickFile = (f: File | null) => {
    if (!f) return;
    const ext = "." + (f.name.split(".").pop() || "").toLowerCase();
    if (!ALLOWED.includes(ext)) {
      setError(t("resumeImp.badFormat", { ext, list: ALLOWED.join(" / ") }));
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(t("resumeImp.tooLarge", { max: MAX_MB }));
      return;
    }
    setError(null);
    setFile(f);
  };

  const runImport = async () => {
    if (!file) return;
    if (!model.trim()) {
      setError(t("resumeImp.modelRequired"));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const content_base64 = await toBase64(file, t("resumeImp.readFailed"));
      const r = await api.importResume({ filename: file.name, content_base64, model: model.trim() });
      setResult(r);
      const d = (r.data || {}) as Record<string, unknown>;
      const b = (d.basics || {}) as Record<string, unknown>;
      setBasics({
        name: String(b.name || ""),
        phone: String(b.phone || ""),
        email: String(b.email || ""),
        location: String(b.location || ""),
      });
      const rest: Record<string, unknown> = {};
      for (const k of ["meta", "education", "projects", "work", "skills", "extras"]) {
        if (k in d) rest[k] = d[k];
      }
      setRestJson(JSON.stringify(rest, null, 2));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const canSave = result && restOk && ack && target.trim();

  const save = async () => {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      const data = {
        ...JSON.parse(restJson),
        basics: {
          name: basics.name,
          phone: basics.phone,
          email: basics.email,
          location: basics.location,
        },
      };
      await api.saveResume(target.trim(), data);
      onImported(target.trim());
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(v) => { if (!v) onClose(); }}>
      <DialogContent className="flex h-[88vh] w-full max-w-5xl flex-col gap-0 p-0">
        {/* 顶栏：Dialog 自带 focus trap / Esc / aria-modal，此前手写遮罩都没有 */}
        <DialogHeader className="flex-row items-center justify-between space-y-0 border-b border-border px-5 py-3">
          <DialogTitle className="flex items-center gap-2 text-sm font-medium">
            <FileUp size={16} className="text-primary" /> {t("resumeImp.title")}
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title={t("common.closeAction")}>
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        {!result ? (
          <div className="flex-1 space-y-5 overflow-y-auto p-5">
            <DialogDescription className="text-sm">
              {t("resumeImp.desc1")}
              <span className="text-warning">{t("resumeImp.desc2")}</span>
              {t("resumeImp.desc3")}
            </DialogDescription>
            <div className="flex items-center gap-3">
              <input
                type="file"
                ref={fileRef}
                className="hidden"
                accept={ALLOWED.join(",")}
                onChange={(e) => pickFile(e.target.files?.[0] || null)}
              />
              <Button variant="outline" onClick={() => fileRef.current?.click()} className="border-dashed">
                <FileUp size={15} /> {t("resumeImp.chooseFile")}
              </Button>
              <span className="text-sm text-muted-foreground">
                {file ? file.name : t("resumeImp.noFile", { max: MAX_MB })}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-sm text-muted-foreground">{t("resumeImp.model")}</Label>
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="deepseek-chat"
                className="w-56"
              />
              <Button onClick={runImport} disabled={!file || busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                {busy ? t("resumeImp.recognizing") : t("resumeImp.recognize")}
              </Button>
            </div>
            {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* 左：原文，供对照 */}
            <div className="w-1/2 overflow-y-auto border-r border-border p-4">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {t("resumeImp.sourceText", { count: result.characters })}
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-foreground">
                {result.text}
              </pre>
            </div>
            {/* 右：结构化字段，可改 */}
            <div className="w-1/2 space-y-3 overflow-y-auto p-4">
              {/* 摘要 */}
              <div className="flex flex-wrap gap-2 text-xs">
                {unfilled.length > 0 && (
                  <Badge variant="warning">
                    {t("resumeImp.unfilled", { fields: unfilled.join("、") })}
                  </Badge>
                )}
                {issues.length > 0 ? (
                  <Badge variant="destructive">
                    {t("resumeImp.suspect", { count: issues.length })}
                  </Badge>
                ) : (
                  <Badge variant="success">{t("resumeImp.allGood")}</Badge>
                )}
              </div>
              {issues.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-destructive/20 bg-destructive/5 p-2 text-[12px] text-destructive">
                  {issues.map((i, idx) => (
                    <li key={idx}>· {i}</li>
                  ))}
                </ul>
              )}
              {/* 关键字段 */}
              <div className="grid grid-cols-2 gap-2">
                {BASICS_KEYS.map(({ key, labelKey, amber }) => {
                  const red = basicsRed(key);
                  const yellow = amber && unfilled.includes(amber);
                  const border = red
                    ? "border-destructive ring-1 ring-destructive/40"
                    : yellow
                    ? "border-warning ring-1 ring-warning/40"
                    : "border-border";
                  return (
                    <div key={key}>
                      <Label className="text-[11px] text-muted-foreground">{t(labelKey)}</Label>
                      <Input
                        value={basics[key] || ""}
                        onChange={(e) => setBasics((b) => ({ ...b, [key]: e.target.value }))}
                        className={border}
                      />
                    </div>
                  );
                })}
              </div>
              {/* 其余结构（教育/项目/工作/技能/其他） */}
              <div>
                <Label className="text-[11px] text-muted-foreground">{t("resumeImp.restLabel")}</Label>
                <Textarea
                  value={restJson}
                  onChange={(e) => setRestJson(e.target.value)}
                  rows={16}
                  spellCheck={false}
                  className={`font-mono text-[12px] ${restOk ? "" : "border-destructive ring-1 ring-destructive/40"}`}
                />
                {!restOk && (
                  <p className="mt-1 text-[12px] text-destructive">{t("resumeImp.jsonInvalid")}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 底栏：确认门禁 */}
        {result && (
          <div className="flex items-center justify-between border-t border-border px-5 py-3">
            <Label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              {t("resumeImp.ack")}
            </Label>
            <div className="flex items-center gap-2">
              <Input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder={t("resumeImp.phTargetVersion")}
                className="w-40"
              />
              <Button onClick={save} disabled={!canSave || busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                {t("resumeImp.confirmWrite")}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
