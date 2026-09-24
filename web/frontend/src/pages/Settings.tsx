import { useEffect, useState, type SyntheticEvent } from "react";
import { useTranslation } from "react-i18next";
import {
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
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import { FormField } from "../components/FormField";
import ThemePicker from "../components/ThemePicker";
import DataPrivacyCard from "../components/settings/DataPrivacyCard";
import SettingsTools from "../components/settings/SettingsTools";
import PreferenceStatusCard from "../components/settings/PreferenceStatusCard";
import { usePreferenceEntries } from "../hooks/usePreferenceEntries";
import {
  modifiedCardIds,
  modifiedCount,
  visibleCardIds,
  type SettingsGroupId,
} from "../lib/settingsRegistry";
import { cn } from "../lib/utils";

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

  // ---- 「找得到」层（笔 4）----
  // 哪些卡可见、哪些项被改过，全由 lib/settingsRegistry 的登记表与纯函数决定；这里只持有
  // 两个 UI 状态（搜索词、分组）。hidden 而不是不渲染：隐藏的卡保留挂载，切回来时不丢状态。
  const { entries, version } = usePreferenceEntries();
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState<SettingsGroupId | "all">("all");
  const cards = visibleCardIds(query, group, modifiedCardIds(entries));
  const hide = (id: string) => cn(!cards.has(id) && "hidden");

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
      <PageHeader title={t("settings.title")} description={t("settings.providerDesc")} />

      <SettingsTools
        query={query}
        onQueryChange={setQuery}
        group={group}
        onGroupChange={setGroup}
        modified={modifiedCount(entries)}
      />

      {cards.size === 0 && (
        <p className="rounded-xl border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
          {t("settings.toolsNoMatch")}
        </p>
      )}

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}
      {info && <ErrorBanner tone="success" message={info} onClose={() => setInfo(null)} />}

      {/* 两列网格：设置页此前是 max-w-2xl 单列——比其它六页窄 45%，切 tab 时内容宽度
          会整块跳变（2026-09-13 实测：672px vs 1232px）。改成与别页同宽之后，单列表单
          会被拉到 1200px 以上，所以按卡片分两列：每张卡仍是"一屏一件事"，字段行长度也
          回到可读范围。items-stretch（用户反馈 #3）：同行卡片等高——此前 items-start
          让各卡按内容自由生长，八张卡高矮不一显得参差；等高后矮卡的留白收进卡内，
          边界整齐。 */}
      <div className="grid items-stretch gap-6 lg:grid-cols-2">
        {/* 外观与偏好状态卡（笔 4）：排在最前——先回答"我改过什么、退得回去吗、什么时候生效" */}
        <PreferenceStatusCard
          entries={entries}
          hidden={!cards.has("prefs")}
          onReset={(entry) => entry.reset?.()}
          onResetAll={() =>
            entries.forEach((entry) => {
              if (entry.modified) entry.reset?.();
            })
          }
        />

        {/* 界面语言：设备级偏好，与下面三张卡（工作区级、随工作区走）不是一类东西，
            所以文案里必须写明"不随工作区导出/同步"——否则用户会以为换台机器会跟着变。
            与顶栏那个分段按钮共用同一个 i18n 实例：两处入口、一份状态，不会打架。 */}
        <Card className={cn("space-y-4 p-5", hide("lang"))}>
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

        {/* 外观（批 4）：主题切换——与语言/大小同为「设备级」偏好（localStorage）。
            选择即生效（只改根属性）；「跟随系统」由 lib/theme 监听系统亮暗自动切换 */}
        <ThemePicker hidden={!cards.has("theme")} version={version} />

        {/* 界面大小：与语言同为「设备级」偏好，紧挨着放。桌面端才有偏好通道——
            浏览器直连时降级成一句说明，而不是把整张卡藏起来：藏起来会让人以为
            功能不存在（那正是这次要修的那类「按了没反应」的老问题）。 */}
        <Card className={cn("space-y-4 p-5", hide("zoom"))}>
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
                  <span className="w-12 shrink-0 text-right text-xs font-medium tabular-nums font-numeric">
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

        <Card className={cn("space-y-4 p-5", hide("provider"))}>
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
              <p className="text-[11px] leading-relaxed text-muted-foreground">
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

        <Card className={cn("space-y-4 p-5", hide("imap"))}>
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
        <Card className={cn("space-y-4 p-5", hide("dataLoc"))}>
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
                <span className="font-mono text-muted-foreground">{paths.dataRoot}</span>
              </p>
              <p className="flex flex-wrap items-center gap-2">
                <Badge variant="outline">
                  {paths.mode === "portable" ? t("settings.modePortable") : t("settings.modeUser")}
                </Badge>
                <span className="text-[11px] leading-relaxed text-muted-foreground">
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
        <Card className={cn("space-y-4 p-5", hide("about"))}>
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
                <span className="text-[11px] text-muted-foreground">
                  {t("settings.aboutVersion")}
                </span>
                <span className="font-mono text-lg font-semibold text-foreground">
                  {paths.appVersion || t("settings.aboutUnknown")}
                </span>
              </p>
              <dl className="space-y-1 text-[11px] text-muted-foreground">
                <div className="flex flex-wrap gap-1.5">
                  <dt className="text-muted-foreground">{t("settings.aboutPlatform")}</dt>
                  <dd className="text-muted-foreground">
                    {({ win32: "Windows", darwin: "macOS", linux: "Linux" } as Record<string, string>)[
                      paths.platform
                    ] || paths.platform || t("settings.aboutUnknown")}
                  </dd>
                </div>
              </dl>
              <p className="text-[11px] leading-relaxed text-muted-foreground">
                {t("settings.aboutNote")}
              </p>
            </div>
          )}
        </Card>

        {/* 数据与隐私卡已拆到 components/settings/DataPrivacyCard.tsx（收口批 笔 2）：
            导出 / 备份 / 打开目录 + 快照列表与还原。拆出去的直接原因是这张卡要长——
            而 Settings.tsx 是登记过水位（693，只许变小）的存量文件。 */}
        <DataPrivacyCard
          paths={paths}
          pathsError={pathsError}
          onReload={loadPaths}
          onError={setError}
          hidden={!cards.has("privacy")}
        />

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
