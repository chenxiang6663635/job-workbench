import { useMemo, useRef, useState } from "react";
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
const BASICS_KEYS = [
  { key: "name", label: "姓名", amber: "姓名" },
  { key: "phone", label: "电话", amber: "电话" },
  { key: "email", label: "邮箱", amber: "邮箱" },
  { key: "location", label: "所在地", amber: "" },
];

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve((r.result as string).split(",")[1] || "");
    r.onerror = () => reject(new Error("文件读取失败"));
    r.readAsDataURL(file);
  });
}

export default function ResumeImportDialog({ currentVersion, onClose, onImported }: Props) {
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

  const issues = result?.issues || [];
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
      setError(`不支持的格式 ${ext}（支持 ${ALLOWED.join(" / ")}）`);
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`文件超过 ${MAX_MB} MB`);
      return;
    }
    setError(null);
    setFile(f);
  };

  const runImport = async () => {
    if (!file) return;
    if (!model.trim()) {
      setError("请填写模型名（如 deepseek-chat）");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const content_base64 = await toBase64(file);
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
            <FileUp size={16} className="text-primary" /> 简历一键导入 · 核对页
          </DialogTitle>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" className="h-7 w-7" title="关闭">
              <X size={16} />
            </Button>
          </DialogClose>
        </DialogHeader>

        {!result ? (
          <div className="flex-1 space-y-5 overflow-y-auto p-5">
            <DialogDescription className="text-sm">
              上传 PDF / Word / Markdown / 纯文本简历 → 抽取文字 → 你的模型结构化为字段。
              <span className="text-warning"> 模型只做「搬运」不做「写作」</span>：
              原文没有的内容会留空，疑似补全的会标红，请你逐段核对后才落盘。
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
                <FileUp size={15} /> 选择文件
              </Button>
              <span className="text-sm text-muted-foreground">{file ? file.name : "未选择（≤10MB）"}</span>
            </div>
            <div className="flex items-center gap-2">
              <Label className="text-sm text-muted-foreground">模型</Label>
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder="deepseek-chat"
                className="w-56"
              />
              <Button onClick={runImport} disabled={!file || busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : null}
                {busy ? "识别中…" : "识别并抽取"}
              </Button>
            </div>
            {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
          </div>
        ) : (
          <div className="flex flex-1 overflow-hidden">
            {/* 左：原文，供对照 */}
            <div className="w-1/2 overflow-y-auto border-r border-border p-4">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                抽取到的原文（{result.characters} 字）· 请逐段对照
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
                  <Badge variant="warning">⚠ 待补填：{unfilled.join("、")}</Badge>
                )}
                {issues.length > 0 ? (
                  <Badge variant="destructive">⛔ 疑似补全 {issues.length} 处，请核对</Badge>
                ) : (
                  <Badge variant="success">✓ 字段全部可在原文中找到</Badge>
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
                {BASICS_KEYS.map(({ key, label, amber }) => {
                  const red = basicsRed(key);
                  const yellow = amber && unfilled.includes(amber);
                  const border = red
                    ? "border-destructive ring-1 ring-destructive/40"
                    : yellow
                    ? "border-warning ring-1 ring-warning/40"
                    : "border-border";
                  return (
                    <div key={key}>
                      <Label className="text-[11px] text-muted-foreground">{label}</Label>
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
                <Label className="text-[11px] text-muted-foreground">其余结构（教育/项目/工作/技能/其他）</Label>
                <Textarea
                  value={restJson}
                  onChange={(e) => setRestJson(e.target.value)}
                  rows={16}
                  spellCheck={false}
                  className={`font-mono text-[12px] ${restOk ? "" : "border-destructive ring-1 ring-destructive/40"}`}
                />
                {!restOk && <p className="mt-1 text-[12px] text-destructive">JSON 解析失败，请检查格式</p>}
              </div>
            </div>
          </div>
        )}

        {/* 底栏：确认门禁 */}
        {result && (
          <div className="flex items-center justify-between border-t border-border px-5 py-3">
            <Label className="flex items-center gap-2 text-sm text-foreground">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              我已逐段核对，原文中没有的内容已删除或改写
            </Label>
            <div className="flex items-center gap-2">
              <Input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                placeholder="目标版本名"
                className="w-40"
              />
              <Button onClick={save} disabled={!canSave || busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <ShieldCheck size={14} />}
                确认无误，写入简历
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
