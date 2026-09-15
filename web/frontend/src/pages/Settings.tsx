import { useEffect, useState, type SyntheticEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Archive,
  Download,
  ExternalLink,
  FolderOpen,
  HardDrive,
  Inbox,
  Info,
  KeyRound,
  Languages,
  Monitor,
  PlugZap,
  Save,
  ShieldCheck,
} from "lucide-react";
import { LANGS } from "../i18n";
import {
  getPrefs,
  hasDesktopPrefs,
  onZoomChanged,
  setZoomLevel,
  type PrefsSnapshot,
} from "../lib/prefs";
import { PROVIDER_REFERRAL } from "../lib/partner";
import {
  api,
  type ImapConfig,
  type ImapTestResult,
  type ProviderConfig,
  type ProviderTestResult,
  type SystemPaths,
} from "../api";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { FormField } from "../components/FormField";

export default function Settings() {
  const { t, i18n } = useTranslation();
  const [cfg, setCfg] = useState<ProviderConfig | null>(null);
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [paths, setPaths] = useState<SystemPaths | null>(null);
  const [pathsError, setPathsError] = useState<string | null>(null);
  const [backing, setBacking] = useState(false);
  const [backupInfo, setBackupInfo] = useState<string | null>(null);

  // 推广入口先摊平成三个非空值：TS 在回调闭包里不做窄化，逐个判空只会更吵
  const refName = PROVIDER_REFERRAL?.name ?? "";
  const refUrl = PROVIDER_REFERRAL?.url ?? "";
  const refPreset = PROVIDER_REFERRAL?.presetBaseUrl ?? "";

  const load = () => {
    api
      .getProvider()
      .then((r) => {
        setCfg(r);
        setBaseUrl(r.base_url);
      })
      .catch((e: Error) => setError(e.message));
  };

  useEffect(load, []);

  // ---- 界面大小（桌面端偏好通道；浏览器里没有通道，降级为一句说明）----
  // 级别真值在主进程（web/electron/main.js）：这里只是它的视图——拖动时预览、
  // 松手时落盘，并按主进程的广播回填（用快捷键调完，滑块会跟着动）。
  const [zoom, setZoom] = useState<PrefsSnapshot | null>(null);
  const desktopPrefs = hasDesktopPrefs();

  useEffect(() => {
    let alive = true;
    getPrefs()?.then((snap) => {
      if (alive) setZoom(snap);
    });
    const off = onZoomChanged((payload) => {
      if (alive) setZoom((s) => (s ? { ...s, level: payload.level, percent: payload.percent } : s));
    });
    return () => {
      alive = false;
      off();
    };
  }, []);

  /** 松手落盘：鼠标/触摸/键盘三类结束路径与失焦都走它。 */
  const commitZoom = (e: SyntheticEvent<HTMLInputElement>) => {
    void setZoomLevel(Number((e.target as HTMLInputElement).value), true);
  };

  // ---- IMAP 只读拉取（B11）----
  const [imapCfg, setImapCfg] = useState<ImapConfig | null>(null);
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState("993");
  const [imapUser, setImapUser] = useState("");
  const [imapPassword, setImapPassword] = useState("");
  const [imapFolder, setImapFolder] = useState("INBOX");
  const [imapSaving, setImapSaving] = useState(false);
  const [imapTesting, setImapTesting] = useState(false);
  const [imapErr, setImapErr] = useState<string | null>(null);
  const [imapMessage, setImapMessage] = useState<string | null>(null);
  const [imapTestResult, setImapTestResult] = useState<ImapTestResult | null>(null);

  const loadImap = () => {
    api
      .getImap()
      .then((r) => {
        setImapCfg(r);
        setImapHost(r.host);
        setImapPort(String(r.port));
        setImapUser(r.user);
        setImapFolder(r.folder || "INBOX");
      })
      .catch((e: Error) => setImapErr(e.message));
  };

  useEffect(loadImap, []);

  const saveImap = () => {
    setImapErr(null);
    setImapMessage(null);
    if (!imapUser.trim()) {
      setImapErr(t("settings.imapEmailRequired"));
      return;
    }
    const port = Number(imapPort);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      setImapErr(t("settings.imapPortRange"));
      return;
    }
    setImapSaving(true);
    api
      .saveImap({
        host: imapHost,
        port,
        user: imapUser,
        password: imapPassword,
        folder: imapFolder,
      })
      .then((r) => {
        setImapCfg(r);
        setImapPassword("");
        setImapMessage(t("settings.imapSaved"));
      })
      .catch((e: Error) => setImapErr(e.message))
      .finally(() => setImapSaving(false));
  };

  const testImap = () => {
    setImapErr(null);
    setImapMessage(null);
    setImapTestResult(null);
    setImapTesting(true);
    api
      .testImap()
      .then((r) => setImapTestResult(r))
      .catch((e: Error) => setImapErr(e.message))
      .finally(() => setImapTesting(false));
  };

  // 路径加载：成功要清掉上一次的错误，否则一次失败会永久盖住后来成功加载的数据
  const loadPaths = () =>
    api
      .systemPaths()
      .then((r) => {
        setPaths(r);
        setPathsError(null);
      })
      .catch((e: Error) => {
        // 控制台日志不是界面文案：保持英文，免得被「残余硬编码中文」检查误伤
      console.error("readPaths failed", e);
        setPathsError(e.message);
      });

  useEffect(() => {
    // 之前是空 catch：失败后页面永远停在骨架上，且错误被静默吞掉（违反「禁静默吞错」）
    loadPaths();
  }, []);

  const backup = () => {
    setError(null);
    setBackupInfo(null);
    setBacking(true);
    api
      .backupWorkspace()
      .then((r) => {
        setBackupInfo(
          t("settings.backupDone", {
            files: r.files,
            size: (r.size / 1024).toFixed(0),
            kept: r.kept,
            removed: r.removed,
          })
        );
        return loadPaths();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setBacking(false));
  };

  const save = () => {
    setError(null);
    setInfo(null);
    setSaving(true);
    api
      .saveProvider({ base_url: baseUrl, api_key: apiKey })
      .then((r) => {
        setCfg(r);
        setApiKey("");
        setInfo(t("settings.saved"));
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(false));
  };

  const test = () => {
    setError(null);
    setInfo(null);
    setTestResult(null);
    setTesting(true);
    api
      .testProvider()
      .then((r) => setTestResult(r))
      .catch((e: Error) => setError(e.message))
      .finally(() => setTesting(false));
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-foreground">{t("settings.title")}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t("settings.providerDesc")}
        </p>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
      {info && <ErrorBanner tone="success" message={info} onClose={() => setInfo(null)} />}

      {/* 两列网格：设置页此前是 max-w-2xl 单列——比其它六页窄 45%，切 tab 时内容宽度
          会整块跳变（2026-09-13 实测：672px vs 1232px）。改成与别页同宽之后，单列表单
          会被拉到 1200px 以上，所以按卡片分两列：每张卡仍是"一屏一件事"，字段行长度也
          回到可读范围。items-start 让卡片各按内容高度，不被同行的最高卡片拉长。 */}
      <div className="grid items-start gap-6 lg:grid-cols-2">
        {/* 界面语言：设备级偏好，与下面三张卡（工作区级、随工作区走）不是一类东西，
            所以文案里必须写明"不随工作区导出/同步"——否则用户会以为换台机器会跟着变。
            与顶栏那个分段按钮共用同一个 i18n 实例：两处入口、一份状态，不会打架。 */}
        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Languages size={16} className="text-primary" /> {t("settings.langTitle")}
            </CardTitle>
          </CardHeader>

          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("settings.langDesc")}
          </p>

          <div className="flex flex-wrap items-center gap-2" role="group"
               aria-label={t("lang.switch")}>
            {LANGS.map((l) => (
              <Button
                key={l.value}
                variant={i18n.language === l.value ? "default" : "outline"}
                className="h-7 px-3 text-xs"
                aria-pressed={i18n.language === l.value}
                onClick={() => i18n.changeLanguage(l.value)}
              >
                {l.label}
              </Button>
            ))}
          </div>
        </Card>

        {/* 界面大小：与语言同为「设备级」偏好，紧挨着放。桌面端才有偏好通道——
            浏览器直连时降级成一句说明，而不是把整张卡藏起来：藏起来会让人以为
            功能不存在（那正是这次要修的那类「按了没反应」的老问题）。 */}
        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Monitor size={16} className="text-primary" /> {t("settings.zoomTitle")}
            </CardTitle>
          </CardHeader>

          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("settings.zoomDesc")}
          </p>

          {desktopPrefs ? (
            zoom ? (
              <>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={zoom.min}
                    max={zoom.max}
                    step={zoom.step}
                    value={zoom.level}
                    aria-label={t("settings.zoomTitle")}
                    className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-muted accent-primary"
                    onChange={(e) => {
                      // 拖动中只预览（persist=false，不落盘）：输入事件本身已按帧调度，
                      // 不再叠一层节流。这里**不回写 IPC 返回值**——拖动很快时旧响应
                      // 可能盖掉新位置（独立审查提的竞态）；百分比松手后由广播校正。
                      const level = Number(e.target.value);
                      setZoom((s) => (s ? { ...s, level } : s));
                      void setZoomLevel(level, false);
                    }}
                    onPointerUp={commitZoom}
                    onPointerCancel={commitZoom}
                    onBlur={commitZoom}
                    onKeyUp={commitZoom}
                  />
                  <span className="w-12 shrink-0 text-right text-xs tabular-nums text-foreground">
                    {zoom.percent}%
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{t("settings.zoomHint")}</p>
              </>
            ) : (
              <Skeleton className="h-1.5 w-full" />
            )
          ) : (
            <p className="text-xs leading-relaxed text-muted-foreground">
              {t("settings.zoomDesktopOnly")}
            </p>
          )}
        </Card>

        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <KeyRound size={16} className="text-primary" /> {t("settings.providerTitle")}
            </CardTitle>
          </CardHeader>

          <div className="space-y-3">
            <FormField label={t("settings.baseUrl")}>
              <Input
                placeholder="https://api.xxx.ai/v1"
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
              />
            </FormField>

            <FormField label={t("settings.apiKey")}>
              <Input
                className="font-mono"
                type="password"
                placeholder={
                  cfg?.hasKey
                    ? t("settings.apiKeySaved", { key: cfg.api_key })
                    : t("settings.apiKeyPlaceholder")
                }
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </FormField>
          </div>

          {/* 推广入口：放在「正好要填 key」的位置，且必须写明它是推广链接。
              藏在一个像官网链接的按钮后面就是欺骗，与本项目的诚实红线冲突。 */}
          {/* 只在「还没存过 key」时出现：已经配好的人不需要这个入口，
              顺带也免掉 cfg 加载完成前的闪一下（cfg 为 null 时不渲染）。 */}
          {cfg && !cfg.hasKey && refUrl && (
            <div className="space-y-1.5 rounded-lg border border-border bg-background/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs text-muted-foreground">
                  {t("settings.referralNoKey")}
                </span>
                <div className="flex flex-wrap items-center gap-2">
                  {/* 端点一键填入：合作方的 Base URL 是固定的 OpenAI 兼容地址，
                      手抄容易错，且错了只会在「测试连接」时才暴露 */}
                  {refPreset && refPreset !== baseUrl && (
                    <Button
                      variant="ghost"
                      className="h-7 px-2.5 text-xs"
                      onClick={() => {
                        setBaseUrl(refPreset);
                        setInfo(t("settings.referralFilled", { name: refName }));
                      }}
                    >
                      {t("settings.referralFill", { name: refName })}
                    </Button>
                  )}
                  <Button asChild variant="outline" className="h-7 px-2.5 text-xs">
                    <a href={refUrl} target="_blank" rel="noopener noreferrer">
                      <ExternalLink size={12} /> {t("settings.referralSignup", { name: refName })}
                    </a>
                  </Button>
                </div>
              </div>
              <p className="text-[11px] leading-relaxed text-muted-foreground/80">
                {t("settings.referralDisclosure")}
                {t("settings.referralNoData")}
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
            <Button onClick={save} disabled={saving}>
              <Save size={15} /> {saving ? t("common.saving") : t("settings.save")}
            </Button>
            <Button variant="outline" onClick={test} disabled={testing}>
              <PlugZap size={15} /> {testing ? t("settings.testing") : t("settings.test")}
            </Button>
          </div>
        </Card>

        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Inbox size={16} className="text-primary" /> {t("settings.imapTitle")}
            </CardTitle>
          </CardHeader>

          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("settings.imapDesc1")}
            {t("settings.imapDesc2")}
            {/* 句号与它后面的空格都在 key 里：写死在 JSX 里会同时出现两个问题——
                英文界面里冒出中文句号，且句末少一个空格（冒烟时抓到） */}
            <span className="text-foreground">{t("settings.imapDesc3")}</span>
            {t("settings.imapDesc4")}
          </p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField label={t("settings.imapEmail")}>
              <Input
                placeholder="your-email@example.com"
                value={imapUser}
                onChange={(e) => setImapUser(e.target.value)}
              />
            </FormField>
            <FormField label={t("settings.imapPassword")}>
              <Input
                className="font-mono"
                type="password"
                placeholder={
                  imapCfg?.hasPassword
                    ? t("settings.imapPasswordSaved", { key: imapCfg.password })
                    : t("settings.imapPasswordHint")
                }
                value={imapPassword}
                onChange={(e) => setImapPassword(e.target.value)}
              />
            </FormField>
            <FormField label={t("settings.imapHost")}>
              <Input
                className="font-mono"
                placeholder={imapCfg?.serverHint || "imap.qq.com"}
                value={imapHost}
                onChange={(e) => setImapHost(e.target.value)}
              />
            </FormField>
            <FormField label={t("settings.imapPort")}>
              <Input
                type="number"
                value={imapPort}
                onChange={(e) => setImapPort(e.target.value)}
              />
            </FormField>
            <FormField label={t("settings.imapFolder")}>
              <Input
                className="font-mono"
                placeholder="INBOX"
                value={imapFolder}
                onChange={(e) => setImapFolder(e.target.value)}
              />
            </FormField>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
            <Button onClick={saveImap} disabled={imapSaving}>
              <Save size={15} /> {imapSaving ? t("common.saving") : t("common.save")}
            </Button>
            <Button variant="outline" onClick={testImap} disabled={imapTesting}>
              <PlugZap size={15} /> {imapTesting ? t("settings.testing") : t("settings.test")}
            </Button>
            {imapMessage && <span className="text-xs text-success">{imapMessage}</span>}
          </div>

          {imapErr && <ErrorBanner message={imapErr} onClose={() => setImapErr(null)} />}

          {imapTestResult && (
            <p className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-muted-foreground">
              {t("settings.imapTestResult", {
                server: imapTestResult.server,
                folder: imapTestResult.folder,
                count: imapTestResult.messageCount,
              })}
            </p>
          )}
        </Card>

        {/* 数据位置：数据根 + 模式（便携 = 应用目录旁；用户目录 = 安装到不可写
            位置时的回退）。与「数据与隐私」相邻：一张回答「数据在哪」，一张
            回答「怎么带走 / 怎么备份」。 */}
        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <HardDrive size={16} className="text-primary" /> {t("settings.dataLocTitle")}
            </CardTitle>
          </CardHeader>

          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("settings.dataLocDesc")}
          </p>

          {/* 三态与「数据与隐私」卡同款：读取失败可定位 / 加载中骨架 / 就绪显示真实路径 */}
          {pathsError ? (
            <p className="text-[11px] text-destructive">
              {t("settings.pathsFailed", { error: pathsError })}
            </p>
          ) : !paths ? (
            <Skeleton className="h-12 w-full" />
          ) : (
            <div className="space-y-1.5">
              <p className="break-all text-[11px] text-muted-foreground">
                {t("settings.dataRoot")}
                <span className="font-mono text-foreground/80">{paths.dataRoot}</span>
              </p>
              <p className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {paths.mode === "portable" ? t("settings.modePortable") : t("settings.modeUser")}
                </Badge>
                <span className="text-[11px] leading-relaxed text-muted-foreground/80">
                  {paths.mode === "portable"
                    ? t("settings.modePortableHint")
                    : t("settings.modeUserHint")}
                </span>
              </p>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              onClick={() => api.openFolder("dataRoot").catch((e: Error) => setError(e.message))}
            >
              <FolderOpen size={15} /> {t("settings.openDataRoot")}
            </Button>
          </div>
        </Card>

        {/* 关于：应用版本 / 运行平台（时间戳体系 2026-09-15）。数据来自 /api/system/paths
            的 appVersion / platform——打包版由 Electron 注入版本、开发模式后端回退读
            package.json；缺失显示「未知」，不编造。显示的是**机器版本**（YY.M.D）：
            N 只在打 tag 那一刻存在，运行时无从派生，发布号请查 tag / CHANGELOG 段名。 */}
        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <Info size={16} className="text-primary" /> {t("settings.aboutTitle")}
            </CardTitle>
          </CardHeader>

          {pathsError ? (
            <p className="text-[11px] text-destructive">
              {t("settings.pathsFailed", { error: pathsError })}
            </p>
          ) : !paths ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <div className="space-y-1.5">
              <p className="flex flex-wrap items-baseline gap-2">
                <span className="text-[11px] text-muted-foreground/80">
                  {t("settings.aboutVersion")}
                </span>
                <span className="text-lg font-semibold tabular-nums text-foreground">
                  {paths.appVersion || t("settings.aboutUnknown")}
                </span>
              </p>
              <dl className="space-y-1 text-[11px] text-muted-foreground">
                <div className="flex flex-wrap gap-1.5">
                  <dt className="text-muted-foreground/80">{t("settings.aboutPlatform")}</dt>
                  <dd className="text-foreground/80">
                    {({ win32: "Windows", darwin: "macOS", linux: "Linux" } as Record<string, string>)[
                      paths.platform
                    ] || paths.platform || t("settings.aboutUnknown")}
                  </dd>
                </div>
              </dl>
              <p className="text-[11px] leading-relaxed text-muted-foreground/80">
                {t("settings.aboutNote")}
              </p>
            </div>
          )}
        </Card>

        <Card className="space-y-4 p-5">
          <CardHeader className="p-0">
            <CardTitle className="flex items-center gap-2 text-sm">
              <ShieldCheck size={16} className="text-success" /> {t("settings.privacy")}
            </CardTitle>
          </CardHeader>

          <p className="text-xs leading-relaxed text-muted-foreground">
            {t("settings.privacyDesc")}
          </p>

          <div className="flex flex-wrap items-center gap-2">
            <Button asChild>
              <a
                href={api.exportUrl()}
                onClick={() =>
                  setBackupInfo(t("settings.exportNotice"))
                }
              >
                <Download size={15} /> {t("settings.exportZip")}
              </a>
            </Button>
            <Button variant="outline" onClick={backup} disabled={backing}>
              <Archive size={15} /> {backing ? t("settings.backingup") : t("settings.backupNow")}
            </Button>
            <Button
              variant="outline"
              onClick={() => api.openFolder("workspace").catch((e: Error) => setError(e.message))}
            >
              <FolderOpen size={15} /> {t("settings.openDataDir")}
            </Button>
          </div>

          {backupInfo && (
            <p className="rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
              {backupInfo}
            </p>
          )}

          <div className="space-y-1 border-t border-border pt-3 text-[11px] text-muted-foreground">
            {/* 三态齐全：加载中骨架 / 读取失败可定位 / 就绪显示真实路径 */}
            {pathsError ? (
              <p className="text-destructive">{t("settings.pathsFailed", { error: pathsError })}</p>
            ) : !paths ? (
              <Skeleton className="h-14 w-full" />
            ) : (
              <>
                <p>
                    {t("settings.lastBackup", {
                      time: paths.lastBackup ?? t("settings.neverBackup"),
                      count: paths.snapshotCount,
                    })}
                </p>
                <p className="break-all">
                  {t("settings.snapshotDir")}
                  {paths.snapshotDir}
                </p>
                <p className="break-all">
                  {t("settings.workspace")}
                  {paths.workspace}
                </p>
              </>
            )}
            <p className="pt-1 text-muted-foreground/70">
              {t("settings.snapshotNote")}
            </p>
          </div>
        </Card>

      </div>

      {testResult && (
        <Card className="space-y-2 border-success/30 bg-success/10 p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-success">
            <PlugZap size={15} /> {t("settings.testOk", { status: testResult.status })}
          </div>
          <p className="text-xs text-muted-foreground">
            {t("settings.modelCount", { count: testResult.modelCount })}
          </p>
          {testResult.models.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {testResult.models.map((m) => (
                <Badge key={m} variant="outline" className="font-mono text-[11px]">
                  {m}
                </Badge>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
