import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  FileCheck,
  FileDown,
  FilePlus2,
  FileText,
  FileUp,
  LayoutTemplate,
  Loader2,
  PenLine,
  Save,
  ShieldAlert,
  X,
} from "lucide-react";
import { api, type ResumeBuildResult, type ResumeVersion } from "../api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Skeleton } from "../components/ui/skeleton";
import ResumeForm from "../components/ResumeForm";
import ResumeTemplates from "../components/ResumeTemplates";
import ResumeImportDialog from "../components/ResumeImportDialog";
import RewritePanel from "../components/RewritePanel";
import VersionLineage from "../components/VersionLineage";

// A4 @96dpi 的像素尺寸。预览区按此比例渲染，超出即触发防超页护栏
const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

type ResumeData = Record<string, unknown>;

// 两种工作对象：数据驱动「标准版式」与手写 HTML「高级模板」
type Mode = "std" | "advanced";

// 与后端 _check_version 一致：只允许字母数字-_
const VERSION_RE = /^[A-Za-z0-9_-]+$/;

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
  // 预览等比缩放：容器比 A4 窄时整体缩小（1:1 渲染会在窄屏显得字大且右侧被裁）
  const [scale, setScale] = useState(1);
  const [showRewrite, setShowRewrite] = useState(false);
  const previewRef = useRef<HTMLDivElement>(null);
  const scaleWrapRef = useRef<HTMLDivElement>(null);
  const [html, setHtml] = useState("");
  // 区分「刚加载」与「用户已编辑」。只有编辑过才自动写回文件——
  // 否则页面一打开就把前端表单规范化后的数据覆盖回去，schema 演进时
  // 表单未表达的字段会被写丢，等于静默损坏用户简历数据。
  const [dirty, setDirty] = useState(false);
  // 工作对象：数据驱动「标准版式」编辑，还是手写「高级模板」浏览
  const [mode, setMode] = useState<Mode>("std");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [creatingBusy, setCreatingBusy] = useState(false);
  const [showImport, setShowImport] = useState(false);

  // 导入核对弹窗：空状态与主视图两条 return 都要挂，否则无简历版本时空状态
  // 提前 return，点开按钮后弹窗根本不渲染。抽成共享节点两处复用。
  const importDialog = showImport && (
    <ResumeImportDialog
      currentVersion={version}
      onClose={() => setShowImport(false)}
      onImported={(name) => {
        setShowImport(false);
        api
          .listResumeVersions()
          .then((r) => {
            setVersions(r.items);
            setVersion(name);
          })
          .catch((e: Error) => setError(e.message));
      }}
    />
  );

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

  // 防超页护栏：测量 iframe 内文档的真实内容高度。
  // 不能靠 addEventListener("load")——useEffect 在 iframe 入 DOM 之后才跑，
  // srcDoc 加载很快时 load 事件已经错过了，量到的永远是空文档高度。
  // 改用 iframe 元素的 onLoad 属性（React 在插入 DOM 前注册），并在字体
  // 与布局稳定后再补量一次。
  const measureOverflow = useCallback(() => {
    const doc = previewRef.current?.querySelector("iframe")?.contentDocument;
    if (!doc) return;
    const h = doc.documentElement?.scrollHeight ?? A4_HEIGHT;
    setOverflowPx(Math.max(0, h - A4_HEIGHT));
  }, []);

  const onPreviewLoad = () => {
    measureOverflow();
    // 字体/图片加载会改变高度，稳定后再量一次
    setTimeout(measureOverflow, 250);
  };

  // 溢出换算成"约几行"（按正文行高 21px 估算）
  const overflowLines = useMemo(
    () => (overflowPx > 0 ? Math.ceil(overflowPx / 21) : 0),
    [overflowPx]
  );

  // 缩放比 = 容器宽 / A4 宽。注意 iframe 布局仍按 1:1（794px）渲染，只缩小显示，
  // 这样换行位置与最终 PDF 完全一致；内容真实高度（含超页）用 A4 高 + overflowPx 推导
  const contentH = A4_HEIGHT + overflowPx;
  useEffect(() => {
    const el = scaleWrapRef.current;
    if (!el) return;
    const fit = () =>
      setScale(Math.min(1, el.clientWidth / A4_WIDTH));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [html]);

  // 用户主动编辑：标记 dirty，触发自动保存与预览刷新
  const edit = (next: ResumeData) => {
    setData(next);
    setDirty(true);
  };

  // 在页面上直接新建标准版式版本（不再要求用户手工去文件系统放 JSON）
  const createVersion = () => {
    const name = newName.trim();
    if (!VERSION_RE.test(name)) {
      setError("版本名只能含字母、数字、-、_");
      return;
    }
    setCreatingBusy(true);
    api
      .saveResume(name, emptyData())
      .then(() => api.listResumeVersions())
      .then((r) => {
        setVersions(r.items);
        setVersion(name);
        setCreating(false);
        setNewName("");
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setCreatingBusy(false));
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

  const modeActive =
    "flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm bg-accent/15 text-accent";
  const modeIdle =
    "flex cursor-pointer items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-secondary/60 hover:text-foreground";

  const errorBanner = error ? (
    <div className="flex items-center justify-between rounded-xl border border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive">
      <span>{error}</span>
      <button onClick={() => setError(null)} className="cursor-pointer">
        <X size={14} />
      </button>
    </div>
  ) : null;

  // 模式切换条 + 标准版式的新建版本入口（两种模式共用顶栏）
  const modeBar = (
    <div className="flex flex-wrap items-center gap-2">
      <button onClick={() => setMode("std")} className={mode === "std" ? modeActive : modeIdle}>
        <PenLine size={16} /> 标准版式
      </button>
      <button onClick={() => setMode("advanced")} className={mode === "advanced" ? modeActive : modeIdle}>
        <LayoutTemplate size={16} /> 高级模板
      </button>

      {mode === "std" && !creating && (
        <>
          <Button
            variant="outline"
            onClick={() => setShowImport(true)}
            className="ml-auto border-dashed"
          >
            <FileUp size={15} /> 导入简历
          </Button>
          <Button
            variant="outline"
            onClick={() => setCreating(true)}
            className="border-dashed"
          >
            <FilePlus2 size={15} /> 新建版本
          </Button>
        </>
      )}
      {mode === "std" && creating && (
        <div className="ml-auto flex items-center gap-2">
          <Input
            autoFocus
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") createVersion();
            }}
            placeholder="版本名，如 hvac / datacenter"
            className="w-56"
          />
          <Button onClick={createVersion} disabled={creatingBusy}>
            {creatingBusy ? <Loader2 size={14} className="animate-spin" /> : null}
            {creatingBusy ? "创建中…" : "创建"}
          </Button>
          <button
            onClick={() => {
              setCreating(false);
              setNewName("");
            }}
            className="cursor-pointer text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            取消
          </button>
        </div>
      )}
    </div>
  );

  if (mode === "advanced") {
    return (
      <div className="space-y-4">
        {errorBanner}
        {modeBar}
        <ResumeTemplates />
      </div>
    );
  }

  if (!version) {
    return (
      <div className="space-y-4">
        {errorBanner}
        {modeBar}
        <div className="rounded-lg border border-dashed border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-10 text-center">
          <FileText size={28} className="mx-auto mb-3 text-muted-foreground" />
          <p className="text-base font-medium text-foreground">还没有标准版式简历数据</p>
          <p className="mt-2 text-sm text-muted-foreground">
            点右上角「新建版本」直接开始编辑，不用手工去文件系统放 JSON。
            手写 HTML 的精排版在「高级模板」里浏览与生成。
          </p>
        </div>
        {importDialog}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {errorBanner}
      {modeBar}

      <div className="flex flex-wrap items-center gap-3">
        <Select value={version} onValueChange={setVersion}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="选择版本" />
          </SelectTrigger>
          <SelectContent>
            {versions.map((v) => (
              <SelectItem key={v.version} value={v.version}>
                {v.version}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button variant="outline" onClick={save} disabled={saving}>
          <Save size={15} /> {saving ? "保存中…" : "保存"}
        </Button>

        <Button
          onClick={build}
          disabled={building || overflowLines > 0}
          title={overflowLines > 0 ? "内容超出一页，先精简再生成" : "生成 PDF 并校验"}
        >
          {building ? <Loader2 size={15} className="animate-spin" /> : <FileCheck size={15} />}
          {building ? "生成中…" : "生成 PDF"}
        </Button>

        <Button
          variant="outline"
          onClick={() => setShowRewrite(true)}
          title="AI 只改写既有事实的表述，反编造校验不过不能采用"
        >
          <PenLine size={15} /> AI 改写
        </Button>

        {/* Word 版定位是「文本搬运」：方便网申系统粘贴。零依赖 .doc，
            排版还原度有限——这一句必须在按钮旁说清，不让用户误当正式交付物 */}
        <Button variant="outline" asChild>
          <a
            href={api.resumeDocUrl(version)}
            download
            title="Word 版只保证文本可复制，排版以 PDF 为准"
          >
            <FileDown size={15} /> 导出 Word
          </a>
        </Button>
        <span className="text-[11px] text-muted-foreground/70">
          Word 版只保证文本可复制，排版以 PDF 为准
        </span>
      </div>

      {/* 左右等分：右列固定上限时窗口稍窄会把表单挤成一细条（1fr 无下限被吃光） */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-border bg-card-gradient shadow-card ring-1 ring-white/5 p-5">
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-warn/25 bg-warn/10 px-3 py-2">
            <ShieldAlert size={15} className="mt-0.5 shrink-0 text-warn" />
            <p className="text-xs leading-relaxed text-muted-foreground">
              内容来自事实库。改动只限于求职方向、概况、技能顺序与项目表述，
              <span className="text-warn">项目事实一个字都不要改</span>——
              每个动词都要经得起五到十分钟的追问。此处不提供一键美化。
            </p>
          </div>
          {data ? (
            <ResumeForm data={data} onChange={edit} />
          ) : (
            <div className="space-y-3">
              {[0, 1, 2, 3, 4].map((i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          )}
        </div>

        {/* 预览列 sticky：左侧表单很长，滚动编辑时预览始终留在视野里 */}
        <div className="space-y-3 lg:sticky lg:top-24 lg:self-start">
          {overflowLines > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
              <AlertTriangle size={14} />
              已超出约 {overflowLines} 行，请先精简内容再生成 PDF
            </div>
          )}

          {/* 留白稍大：纸张若正好铺满容器会显得内容贴边、像被裁 */}
          <div className="overflow-hidden rounded-lg border border-border bg-background/60 p-6">
            {/* 缩放壳量可用宽度；内层按 1:1 渲染再等比缩小，换行与 PDF 一致且永不裁剪 */}
            <div
              ref={scaleWrapRef}
              className="mx-auto overflow-hidden"
              style={{ height: contentH * scale }}
            >
              <div
                className="origin-top-left bg-white shadow-elevated"
                style={{
                  width: A4_WIDTH,
                  transform: `scale(${scale})`,
                  transformOrigin: "top left",
                }}
              >
                <div ref={previewRef}>
                  {html ? (
                    <iframe
                      title="简历预览"
                      srcDoc={html}
                      onLoad={onPreviewLoad}
                      className="w-full border-0"
                      style={{ height: contentH }}
                    />
                  ) : (
                    <div
                      className="flex items-center justify-center text-sm text-muted-foreground"
                      style={{ height: A4_HEIGHT }}
                    >
                      预览生成中…
                    </div>
                  )}
                </div>
              </div>
            </div>
            {scale < 1 && (
              <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
                预览已缩放至 {Math.round(scale * 100)}%（布局与生成 PDF 一致）
              </p>
            )}
          </div>

          {result && (
            <div
              className={`rounded-lg border p-5 ${
                result.passed
                  ? "border-good/30 bg-good/10"
                  : "border-destructive/30 bg-destructive/10"
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">
                  {result.passed ? "生成成功，ATS 校验通过" : "生成完成，校验未通过"}
                </span>
                <span className="font-mono text-xs text-muted-foreground">
                  {(result.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li className="flex items-center justify-between">
                  <span className="text-muted-foreground">纸型</span>
                  <span className={result.a4.ok ? "text-good" : "text-destructive"}>
                    {result.a4.message}
                  </span>
                </li>
                {result.checks.map((c) => (
                  <li key={c.label} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{c.label}</span>
                    <span
                      className={
                        c.ok === null ? "text-muted-foreground" : c.ok ? "text-good" : "text-destructive"
                      }
                    >
                      {c.value}
                    </span>
                  </li>
                ))}
              </ul>
              {!result.passed && (
                <p className="mt-3 text-xs text-muted-foreground">
                  未通过时不要归档投递。删减原则：先删装饰性内容，
                  绝不删核心成果与可验证数字。
                </p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* 版本谱系：该版本投了哪些岗位、各处于什么阶段（只读） */}
      <VersionLineage />

      {showRewrite && data && (
        <RewritePanel
          version={version}
          original={data}
          onClose={() => setShowRewrite(false)}
          onApply={(suggestion) => {
            setData(suggestion as ResumeData);
            setShowRewrite(false);
          }}
        />
      )}

      {importDialog}
    </div>
  );
}
