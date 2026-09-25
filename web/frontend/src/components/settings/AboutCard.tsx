import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";
import type { SystemPaths } from "../../api";

/** 「关于」卡：应用版本 / 运行平台 / 使用手册入口。
 *
 *  从 Settings.tsx 抽出（评分放宽批：加文档入口时顺带抽取，Settings.tsx 只许变小）。
 *  数据来自 /api/system/paths 的 appVersion / platform——打包版由 Electron 注入
 *  版本、开发模式后端回退读 package.json；缺失显示「未知」，不编造。
 *  显示的就是**完整版本号**（月粒度 CalVer `YY.MM.N`，如 26.9.0）——tag /
 *  CHANGELOG 段名 / package.json / 界面显示是同一个号（2026-09-24 起，不再有
 *  "tag 才有的第 4 段"）。
 *
 *  文档入口是四端里性价比最高的一处：桌面端与 Web 共用这套前端（桌面端没有
 *  菜单栏可加），改这里 = 两端同时获得「卡住时去哪儿看文档」的路。 */
export default function AboutCard({
  paths,
  pathsError,
  hidden,
}: {
  paths: SystemPaths | null;
  pathsError: string | null;
  hidden: boolean;
}) {
  const { t, i18n } = useTranslation();
  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
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
          <a
            className="text-[11px] text-primary hover:underline"
            href={`https://github.com/chenxiang6663635/job-workbench/blob/main/docs/usage-guide${
              i18n.language.startsWith("en") ? "" : ".zh-CN"
            }.md`}
            target="_blank"
            rel="noreferrer"
          >
            {t("settings.aboutDocs")}
          </a>
        </div>
      )}
    </Card>
  );
}
