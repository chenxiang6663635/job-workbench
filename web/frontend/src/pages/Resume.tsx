import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  FileCheck,
  FileText,
  Loader2,
  Save,
  ShieldAlert,
  X,
} from "lucide-react";
import { api, type ResumeBuildResult, type ResumeVersion } from "../api";
import ResumeForm from "../components/ResumeForm";

// A4 @96dpi 的像素尺寸。预览区按此比例渲染，超出即触发防超页护栏
const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

type ResumeData = Record<string, unknown>;

function emptyData(): ResumeData {
  return {
    meta: { intent: "", profile: "" },
    basics: { name: "", phone: "", email: "", location: "" },
    education: [],
    projects: [],
    work: [],
    skills: [],
    extras: { research: [], awards: "", certificates: "" },
  };
}

export default function Resume() {
  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [version, setVersion] = useState("");
  const [data, setData] = useState<ResumeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<ResumeBuildResult | null>(null);
  const [overflowPx, setOverflowPx] = useState(0);
  const previewRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  // 区分「刚加载」与「用户已编辑」。只有编辑过才自动写回文件——
  // 否则页面一打开就把前端表单规范化后的数据覆盖回去，schema 演进时
  // 表单未表达的字段会被写丢，等于静默损坏用户简历数据。
  const [dirty, setDirty] = useState(false);

  // 载入版本列表
  useEffect(() => {
    api
      .listResumeVersions()
      .then((r) => {
        setVersions(r.items);
        if (r.items.length && !version) setVersion(r.items[0].version);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // 载入选中版本的数据
  useEffect(() => {
    if (!version) return;
    setResult(null);
    setDirty(false); // 加载不算编辑，避免打开页面就写回
    api
      .getResume(version)
      .then((r) => setData((r.data ?? emptyData()) as ResumeData))
      .catch((e: Error) => setError(e.message));
  }, [version]);

  // 预览 HTML：编辑后防抖保存再重取预览；仅加载时只取预览不写回
  useEffect(() => {
    if (!version || !data) return;
    const timer = setTimeout(
      () => {
        const saved = dirty
          ? api.saveResume(version, data)
          : Promise.resolve<unknown>(null);
        saved
          .then(() => api.resumeHtml(version))
          .then((r) => setHtml(r.html))
          .catch((e: Error) => setError(e.message));
      },
      dirty ? 400 : 0
    );
    return () => clearTimeout(timer);
  }, [data, version, dirty]);

  // 防超页护栏：测量预览内容的实际高度
  useEffect(() => {
    const el = previewRef.current;
    if (!el) return;
    const measure = () => setOverflowPx(Math.max(0, el.scrollHeight - A4_HEIGHT));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [html]);

  // 溢出换算成"约几行"（按正文行高 21px 估算）
  const overflowLines = useMemo(
    () => (overflowPx > 0 ? Math.ceil(overflowPx / 21) : 0),
    [overflowPx]
  );

  // 用户主动编辑：标记 dirty，触发自动保存与预览刷新
  const edit = (next: ResumeData) => {
    setData(next);
    setDirty(true);
  };

  const save = () => {
    if (!version || !data) return;
    setSaving(true);
    api
      .saveResume(version, data)
      .then(() => api.listResumeVersions())
      .then((r) => setVersions(r.items))
      .then(() => setDirty(false))
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false));
  };

  const build = () => {
    if (!version) return;
    setBuilding(true);
    setResult(null);
    api
      .buildResume(version)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBuilding(false));
  };

  const inputCls =
    "rounded-lg border border-white/10 bg-ink-900 px-3 py-2 text-sm text-slate-200 outline-none transition-colors focus:border-accent/60";

  if (!version) {
    return (
      <div className="rounded-2xl border border-dashed border-white/15 bg-ink-900/50 p-10 text-center">
        <FileText size={28} className="mx-auto mb-3 text-slate-500" />
        <p className="text-base font-medium text-slate-200">还没有标准版式简历数据</p>
        <p className="mt-2 text-sm text-slate-400">
          在 <code className="rounded bg-ink-950 px-1.5 py-0.5">02_简历工坊/source/</code>{" "}
          下放一份 <code className="rounded bg-ink-950 px-1.5 py-0.5">resume_&lt;版本&gt;.json</code>{" "}
          即可开始编辑。现有手写 HTML 的精排版本不受影响，仍在素材库中浏览。
        </p>
      </div>
    );
  }

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
        <select
          value={version}
          onChange={(e) => setVersion(e.target.value)}
          className={`${inputCls} cursor-pointer`}
        >
          {versions.map((v) => (
            <option key={v.version} value={v.version}>
              {v.version}
            </option>
          ))}
        </select>

        <button
          onClick={save}
          disabled={saving}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-white/10 px-3 py-2 text-sm text-slate-200 transition-colors hover:bg-white/5 disabled:opacity-40"
        >
          <Save size={15} /> {saving ? "保存中…" : "保存"}
        </button>

        <button
          onClick={build}
          disabled={building || overflowLines > 0}
          title={overflowLines > 0 ? "内容超出一页，先精简再生成" : "生成 PDF 并校验"}
          className="flex cursor-pointer items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 transition-all hover:bg-accent-soft active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {building ? <Loader2 size={15} className="animate-spin" /> : <FileCheck size={15} />}
          {building ? "生成中…" : "生成 PDF"}
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,820px)]">
        <div className="rounded-2xl border border-white/10 bg-ink-900/60 p-5">
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-warn/25 bg-warn/10 px-3 py-2">
            <ShieldAlert size={15} className="mt-0.5 shrink-0 text-warn" />
            <p className="text-xs leading-relaxed text-slate-300">
              内容来自事实库。改动只限于求职方向、概况、技能顺序与项目表述，
              <span className="text-warn">项目事实一个字都不要改</span>——
              每个动词都要经得起五到十分钟的追问。此处不提供一键美化。
            </p>
          </div>
          {data ? (
            <ResumeForm data={data} onChange={edit} />
          ) : (
            <p className="text-sm text-slate-500">载入中…</p>
          )}
        </div>

        <div className="space-y-3">
          {overflowLines > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
              <AlertTriangle size={14} />
              已超出约 {overflowLines} 行，请先精简内容再生成 PDF
            </div>
          )}

          <div className="overflow-hidden rounded-2xl border border-white/10 bg-ink-950/60 p-4">
            <div
              className="mx-auto origin-top bg-white"
              style={{ width: A4_WIDTH, maxWidth: "100%" }}
            >
              <div ref={previewRef}>
                {html ? (
                  <iframe
                    title="简历预览"
                    srcDoc={html}
                    className="w-full border-0"
                    style={{ height: A4_HEIGHT }}
                  />
                ) : (
                  <div
                    className="flex items-center justify-center text-sm text-slate-500"
                    style={{ height: A4_HEIGHT }}
                  >
                    预览生成中…
                  </div>
                )}
              </div>
            </div>
          </div>

          {result && (
            <div
              className={`rounded-2xl border p-5 ${
                result.passed
                  ? "border-good/30 bg-good/10"
                  : "border-bad/30 bg-bad/10"
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-slate-200">
                  {result.passed ? "生成成功，ATS 校验通过" : "生成完成，校验未通过"}
                </span>
                <span className="font-mono text-xs text-slate-400">
                  {(result.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li className="flex items-center justify-between">
                  <span className="text-slate-400">纸型</span>
                  <span className={result.a4.ok ? "text-good" : "text-bad"}>
                    {result.a4.message}
                  </span>
                </li>
                {result.checks.map((c) => (
                  <li key={c.label} className="flex items-center justify-between">
                    <span className="text-slate-400">{c.label}</span>
                    <span
                      className={
                        c.ok === null ? "text-slate-500" : c.ok ? "text-good" : "text-bad"
                      }
                    >
                      {c.value}
                    </span>
                  </li>
                ))}
              </ul>
              {!result.passed && (
                <p className="mt-3 text-xs text-slate-400">
                  未通过时不要归档投递。删减原则：先删装饰性内容，
                  绝不删核心成果与可验证数字。
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
