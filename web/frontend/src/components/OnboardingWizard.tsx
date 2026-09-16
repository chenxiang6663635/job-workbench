/**
 * 首启引导：从「装完是一片空白」走到「有一个能用的工作区」。
 *
 * 两层结构：
 * - `EmptyOnboarding`：首页空态卡（新建 / 示例 / 继续用现有），自包含地管理向导开关
 *   ——这样首页只改一行，空态的全部逻辑都在这个文件里；
 * - `OnboardingWizard`：三步对话框（命名 → 选领域 → 确认创建）。
 *
 * 第三步展示的是**后端算出来的清单**（新建几个文件、会不会覆盖什么），确认后
 * 拿一次性令牌落盘——与命令行同一套两段式协议，网页端不另写一份初始化。
 * 创建成功后提示「开始使用」并刷新：新工作区会被后端列出来，用户直接进入界面。
 *
 * 注意：**接口失败不等于没有数据**。空态只在后端成功返回 `total === 0` 时由
 * 首页渲染（见 Dashboard 的三分支），这个组件自己不做"有没有数据"的判断。
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, ArrowLeft, Check, FolderPlus, Loader2, Sparkles } from "lucide-react";
import { api, type WorkspacePreviewResult } from "../api";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "./ui/input";

// 与后端 _resolve_new_workspace 同口径：只收单个目录名。前端先拦一道是为了
// 让用户在输入时就看见问题，而不是点完「下一步」才收到 422。
const NAME_PATTERN = /^[^/\\]+$/;

export function EmptyOnboarding() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [demoFirst, setDemoFirst] = useState(false);

  const start = (demo: boolean) => {
    setDemoFirst(demo);
    setOpen(true);
  };

  return (
    <div className="mx-auto max-w-2xl pt-6">
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card-gradient p-10 text-center shadow-card ring-1 ring-highlight/5">
        <span className="flex h-12 w-12 items-center justify-center rounded-full border border-primary/40 text-primary">
          <FolderPlus size={22} />
        </span>
        <h2 className="text-lg font-semibold text-foreground">
          {t("onboard.emptyTitle")}
        </h2>
        <p className="max-w-md text-sm text-muted-foreground">
          {t("onboard.emptyHint")}
        </p>
        <div className="mt-2 flex gap-3">
          <Button onClick={() => start(false)}>{t("onboard.startCta")}</Button>
          <Button variant="outline" onClick={() => start(true)}>
            {t("onboard.explore")}
          </Button>
        </div>
      </div>
      <OnboardingWizard open={open} onOpenChange={setOpen} demoFirst={demoFirst} />
    </div>
  );
}

export function OnboardingWizard({
  open,
  onOpenChange,
  demoFirst = false,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  demoFirst?: boolean;
}) {
  const { t } = useTranslation();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("personal");
  const [domains, setDomains] = useState<{ id: string; isDemoDefault: boolean }[]>([]);
  const [domain, setDomain] = useState("");
  const [demo, setDemo] = useState(demoFirst);
  const [preview, setPreview] = useState<WorkspacePreviewResult | null>(null);
  const [created, setCreated] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setDemo(demoFirst);
    setError("");
    api
      .listDomains()
      .then((body) => {
        setDomains(body.items);
        const preferred =
          body.items.find((item) => item.isDemoDefault)?.id ?? body.items[0]?.id ?? "";
        setDomain((prev) => prev || preferred);
      })
      .catch((e: Error) => setError(e.message));
  }, [open, demoFirst]);

  const trimmed = name.trim();
  const nameOk = trimmed.length > 0 && NAME_PATTERN.test(trimmed);

  const close = () => {
    onOpenChange(false);
    setStep(1);
    setPreview(null);
    setCreated("");
    setError("");
  };

  const runPreview = () => {
    setBusy(true);
    setError("");
    api
      .previewWorkspace({ name: trimmed, domain: domain || undefined, demo })
      .then((body) => {
        setPreview(body);
        setStep(3);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const runApply = () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    api
      .applyWorkspace(preview.token)
      .then(() => setCreated(preview.path))
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const stepLabels = [t("onboard.step1"), t("onboard.step2"), t("onboard.step3")];

  return (
    <Dialog
      open={open}
      // 进行中与创建成功都不允许关闭：前者会留下半成品工作区，后者会让用户
      // 还没点到「开始使用」就把路径提示弄丢（独立审查 MINOR-2）。
      onOpenChange={(next) => (next || busy || created ? undefined : close())}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {created ? t("onboard.done") : t("onboard.title")}
          </DialogTitle>
          <DialogDescription>
            {created ? t("onboard.doneHint") : t("onboard.subtitle")}
          </DialogDescription>
        </DialogHeader>

        {!created && (
          <div className="flex items-center gap-2">
            {stepLabels.map((label, index) => {
              const value = index + 1;
              return (
                <div key={label} className="flex flex-1 items-center gap-2">
                  <span
                    className={
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[11px] " +
                      (value < step
                        ? "bg-primary/20 text-primary"
                        : value === step
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground")
                    }
                  >
                    {value < step ? <Check size={12} /> : value}
                  </span>
                  <span
                    className={
                      "truncate text-xs " +
                      (value === step ? "text-foreground" : "text-muted-foreground")
                    }
                  >
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {created ? (
          <div className="space-y-3">
            <p className="break-all rounded-md bg-muted/40 p-2 font-mono text-[11px] text-foreground">
              {created}
            </p>
            <Button className="w-full" onClick={() => window.location.reload()}>
              {t("onboard.start")}
            </Button>
          </div>
        ) : step === 1 ? (
          <div className="space-y-2">
            <label htmlFor="onboard-name" className="text-sm font-medium text-foreground">
              {t("onboard.nameLabel")}
            </label>
            <Input
              id="onboard-name"
              value={name}
              autoFocus
              onChange={(event) => setName(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t("onboard.nameHelp")}</p>
            {!nameOk && trimmed.length > 0 && (
              <p className="text-xs text-destructive">{t("onboard.nameInvalid")}</p>
            )}
          </div>
        ) : step === 2 ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">{t("onboard.domainHelp")}</p>
            <div className="space-y-1">
              {domains.map((item) => (
                <label
                  key={item.id}
                  className={
                    "flex cursor-pointer items-center gap-2 rounded-md border p-2.5 text-sm " +
                    (domain === item.id ? "border-primary/50" : "border-border")
                  }
                >
                  <input
                    type="radio"
                    name="onboard-domain"
                    checked={domain === item.id}
                    onChange={() => setDomain(item.id)}
                  />
                  <span className="font-mono text-xs">{item.id}</span>
                  {item.isDemoDefault && (
                    <span className="rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {t("onboard.demoTag")}
                    </span>
                  )}
                </label>
              ))}
            </div>
            <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
              <input
                type="checkbox"
                checked={demo}
                onChange={(event) => setDemo(event.target.checked)}
              />
              {t("onboard.demoLabel")}
            </label>
            <p className="text-xs text-muted-foreground">{t("onboard.demoHelp")}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm font-medium text-foreground">{preview?.summary}</p>
            <ul className="max-h-44 space-y-0.5 overflow-auto rounded-md bg-muted/40 p-2 font-mono text-[11px] text-muted-foreground">
              {preview?.diff.map((line) => <li key={line}>{line}</li>)}
            </ul>
            <p className="break-all text-xs text-muted-foreground">
              {t("onboard.pathLabel")}：<span className="font-mono">{preview?.path}</span>
            </p>
          </div>
        )}

        <DialogFooter>
          {!created && step > 1 && (
            <Button variant="ghost" onClick={() => setStep((value) => value - 1)} disabled={busy}>
              <ArrowLeft size={14} />
              {t("onboard.prev")}
            </Button>
          )}
          {created ? null : step < 3 ? (
            <Button
              onClick={() => (step === 2 ? runPreview() : setStep(2))}
              disabled={busy || (step === 1 && !nameOk)}
            >
              {busy && <Loader2 size={14} className="animate-spin" />}
              {step === 2 ? t("onboard.preview") : t("onboard.next")}
            </Button>
          ) : (
            <Button onClick={runApply} disabled={busy}>
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {busy ? t("onboard.creating") : t("onboard.create")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
