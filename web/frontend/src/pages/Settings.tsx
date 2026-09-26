import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { FolderOpen, HardDrive, Languages } from "lucide-react";
import { LANGS } from "../i18n";
import { api, type SystemPaths } from "../api";
import { Button } from "../components/ui/button";
import { Card, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { PageHeader } from "../components/ui/page-header";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import ThemePicker from "../components/ThemePicker";
import DataPrivacyCard from "../components/settings/DataPrivacyCard";
import ZoomCard from "../components/settings/ZoomCard";
import AboutCard from "../components/settings/AboutCard";
import ImapCard from "../components/settings/ImapCard";
import ProviderCard from "../components/settings/ProviderCard";
import SettingsTools from "../components/settings/SettingsTools";
import PreferenceStatusCard from "../components/settings/PreferenceStatusCard";
import { usePreferenceEntries } from "../hooks/usePreferenceEntries";
import {
  filterEntries,
  modifiedCardIds,
  modifiedCount,
  visibleCardIds,
  type SettingsGroupId,
} from "../lib/settingsRegistry";
import { cn } from "../lib/utils";

export default function Settings() {
  const { t, i18n } = useTranslation();
  // Provider 卡的状态（草稿 / 测试结果 / 推广提示）已随卡搬到 ProviderCard；
  // 页面只留一个跨卡的错误通道（路径读取、备份、打开目录都往这里报）
  const [error, setError] = useState<string | null>(null);
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

  // IMAP 卡已整块搬到 components/settings/ImapCard.tsx（邮箱配置批）：它的状态
  // （凭证草稿、脏标记、文件夹候选）只在那张卡里用得到，页面代持只会两头难读。

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

      {/* 路径读取失败平时显示在「数据位置 / 关于 / 数据与隐私」三张卡里；这三张都被筛掉时
          提到页面级——否则用户切到别的分组后看到的是"一片空白"（批末审查指出的静默吞错） */}
      {pathsError && !cards.has("dataLoc") && !cards.has("about") && !cards.has("privacy") && (
        <ErrorBanner
          message={t("settings.pathsFailed", { error: pathsError })}
          onClose={() => setPathsError(null)}
        />
      )}

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 两列网格：设置页此前是 max-w-2xl 单列——比其它六页窄 45%，切 tab 时内容宽度
          会整块跳变（2026-09-13 实测：672px vs 1232px）。改成与别页同宽之后，单列表单
          会被拉到 1200px 以上，所以按卡片分两列：每张卡仍是"一屏一件事"，字段行长度也
          回到可读范围。items-stretch（用户反馈 #3）：同行卡片等高——此前 items-start
          让各卡按内容自由生长，八张卡高矮不一显得参差；等高后矮卡的留白收进卡内，
          边界整齐。 */}
      <div className="grid items-stretch gap-6 lg:grid-cols-2">
        {/* 外观与偏好状态卡（笔 4）：排在最前——先回答"我改过什么、退得回去吗、什么时候生效" */}
        <PreferenceStatusCard
          entries={filterEntries(entries, query)}
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

        {/* 界面大小卡已拆到 components/settings/ZoomCard.tsx（收口批）：
            拆出去的直接原因是 Settings.tsx 是登记过水位（旧 693，只许变小）的存量文件，
            拆完跌破 300 阈值，按自洁规则同步删掉了 size_allowlist 的那一行 */}
        <ZoomCard hidden={!cards.has("zoom")} />

        {/* 模型服务卡整块在 components/settings/ProviderCard.tsx（模型服务批）：
            服务商预设、默认模型、模型可点选都在那边，状态也由它自持。 */}
        <ProviderCard hidden={!cards.has("provider")} />

        {/* 邮箱卡整块在 components/settings/ImapCard.tsx（本批）：服务商下拉、
            授权码引导、文件夹候选都在那边，状态也由它自持。 */}
        <ImapCard hidden={!cards.has("imap")} />

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

        {/* 关于卡已拆到 components/settings/AboutCard.tsx（评分放宽批：加使用手册
            入口时顺带抽取——桌面端与 Web 共用这套前端，文档入口两端同时获得） */}
        <AboutCard paths={paths} pathsError={pathsError} hidden={!cards.has("about")} />

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
    </div>
  );
}
