import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
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
import { Card } from "../components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ErrorBanner } from "../components/ErrorBanner";
// A4_HEIGHT 是防超页护栏的基准，宽高常量统一由 A4Preview 定义（单一真值源）
import { A4Preview, A4_HEIGHT } from "../components/A4Preview";
import ResumeForm from "../components/ResumeForm";
import ResumeTemplates from "../components/ResumeTemplates";
import ResumeImportDialog from "../components/ResumeImportDialog";
import RewritePanel from "../components/RewritePanel";
import VersionLineage from "../components/VersionLineage";

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
  const { t } = useTranslation();
  const [versions, setVersions] = useState<ResumeVersion[]>([]);
  const [version, setVersion] = useState("");
  const [data, setData] = useState<ResumeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [building, setBuilding] = useState(false);
  const [result, setResult] = useState<ResumeBuildResult | null>(null);
  // 防超页护栏：A4Preview 回传内容真实高度，超出 A4 的像素量
  const [overflowPx, setOverflowPx] = useState(0);
  const [showRewrite, setShowRewrite] = useState(false);
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
        // 函数式更新：不引用外层 version，挂载语义（[] 依赖）才成立
        if (r.items.length) setVersion((cur) => cur || r.items[0].version);
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

  // 在页面上直接新建标准版式版本（不再要求用户手工去文件系统放 JSON）
  const createVersion = () => {
    const name = newName.trim();
    if (!VERSION_RE.test(name)) {
      setError(t("resume.versionNameInvalid"));
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

  const errorBanner = error ? (
    <ErrorBanner message={error} onClose={() => setError(null)} />
  ) : null;

  // 模式切换条 + 标准版式的新建版本入口（两种模式共用顶栏）
  // 此前是两个裸 button 拼 modeActive/modeIdle 两个 class 串——改用 ui/tabs
  const modeBar = (
    <div className="flex flex-wrap items-center gap-2">
      <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
        <TabsList>
          <TabsTrigger value="std" className="gap-1.5">
            <PenLine size={16} /> {t("resume.modeStd")}
          </TabsTrigger>
          <TabsTrigger value="advanced" className="gap-1.5">
            <LayoutTemplate size={16} /> {t("resume.modeAdvanced")}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {mode === "std" && !creating && (
        <>
          <Button
            variant="outline"
            onClick={() => setShowImport(true)}
            className="ml-auto border-dashed"
          >
            <FileUp size={15} /> {t("resume.importResume")}
          </Button>
          <Button
            variant="outline"
            onClick={() => setCreating(true)}
            className="border-dashed"
          >
            <FilePlus2 size={15} /> {t("resume.newVersion")}
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
            placeholder={t("resume.phVersionName")}
            className="w-56"
          />
          <Button onClick={createVersion} disabled={creatingBusy}>
            {creatingBusy ? <Loader2 size={14} className="animate-spin" /> : null}
            {creatingBusy ? t("resume.creating") : t("resume.create")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => {
              setCreating(false);
              setNewName("");
            }}
          >
              {t("common.cancel")}
          </Button>
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
        <Card className="border-dashed p-10 text-center">
          <FileText size={28} className="mx-auto mb-3 text-muted-foreground" />
          <p className="text-base font-medium text-foreground">{t("resume.emptyTitle")}</p>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("resume.emptyHint1")}
            {t("resume.emptyHint2")}
          </p>
        </Card>
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
            <SelectValue placeholder={t("resume.selectVersion")} />
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
          <Save size={15} /> {saving ? t("common.saving") : t("common.save")}
        </Button>

        <Button
          onClick={build}
          disabled={building || overflowLines > 0}
          title={t(overflowLines > 0 ? "resume.buildBlocked" : "resume.buildTitle")}
        >
          {building ? <Loader2 size={15} className="animate-spin" /> : <FileCheck size={15} />}
          {building ? t("resume.building") : t("resume.buildPdf")}
        </Button>

        <Button
          variant="outline"
          onClick={() => setShowRewrite(true)}
          title={t("resume.rewriteTitle")}
        >
          <PenLine size={15} /> {t("resume.aiRewrite")}
        </Button>

        {/* Word 版定位是「文本搬运」：方便网申系统粘贴。零依赖 .doc，
            排版还原度有限——这一句必须在按钮旁说清，不让用户误当正式交付物 */}
        <Button variant="outline" asChild>
          <a
            href={api.resumeDocUrl(version)}
            download
            title={t("resume.wordTitle")}
          >
            <FileDown size={15} /> {t("resume.exportWord")}
          </a>
        </Button>
        <span className="text-[11px] text-muted-foreground/70">
          {t("resume.wordTitle")}
        </span>
      </div>

      {/* 左右等分：右列固定上限时窗口稍窄会把表单挤成一细条（1fr 无下限被吃光） */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="p-5">
          <div className="mb-3 flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2">
            <ShieldAlert size={15} className="mt-0.5 shrink-0 text-warning" />
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("resume.stdNote1")}
              <span className="text-warning">{t("resume.stdNote2")}</span>
              {t("resume.stdNote3")}
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
        </Card>

        {/* 预览列 sticky：左侧表单很长，滚动编辑时预览始终留在视野里 */}
        <div className="space-y-3 lg:sticky lg:top-24 lg:self-start">
          {overflowLines > 0 && (
            <ErrorBanner
              tone="warning"
              message={t("resume.overflowMsg", { lines: overflowLines })}
            />
          )}

          {/* A4 预览：此前内联实现与 ResumeTemplates 的 TemplatePreview 重复，
              已抽为公共组件 A4Preview（等比缩放 + 真实内容高度回调） */}
          {html ? (
            <A4Preview
              html={html}
              title={t("a4.previewTitle")}
              onHeight={(h) => setOverflowPx(Math.max(0, h - A4_HEIGHT))}
            />
          ) : (
            <Skeleton className="h-[36rem] w-full" />
          )}

          {result && (
            <Card
              className={`p-5 ${
                result.passed
                  ? "border-success/30 bg-success/10"
                  : "border-destructive/30 bg-destructive/10"
              }`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold text-foreground">
                  {result.passed ? t("resume.buildOk") : t("resume.buildFailed")}
                </span>
                <span className="font-mono text-xs text-muted-foreground">
                  {(result.size / 1024).toFixed(1)} KB
                </span>
              </div>
              <ul className="space-y-1 text-xs">
                <li className="flex items-center justify-between">
                  <span className="text-muted-foreground">{t("resume.paperSize")}</span>
                  <span className={result.a4.ok ? "text-success" : "text-destructive"}>
                    {result.a4.message}
                  </span>
                </li>
                {result.checks.map((c) => (
                  <li key={c.label} className="flex items-center justify-between">
                    <span className="text-muted-foreground">{c.label}</span>
                    <span
                      className={
                        c.ok === null ? "text-muted-foreground" : c.ok ? "text-success" : "text-destructive"
                      }
                    >
                      {c.value}
                    </span>
                  </li>
                ))}
              </ul>
              {!result.passed && (
                <p className="mt-3 text-xs text-muted-foreground">
                  {t("resume.atsHint1")}
                  {t("resume.atsHint2")}
                </p>
              )}
            </Card>
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
