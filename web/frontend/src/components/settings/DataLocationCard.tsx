import { useTranslation } from "react-i18next";
import { FolderOpen, HardDrive } from "lucide-react";
import { api, type DataRootDiagnostic, type SystemPaths } from "../../api";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";
import MigrateFlow from "./MigrateFlow";

/**
 * 「数据位置」卡（B2 从 Settings.tsx 拆出——该页是登记过水位的存量文件）。
 *
 * 回答「数据现在在哪、可靠吗」：诊断对象与 CLI doctor / MCP jobws.info 同源；
 * 四态徽章在失效与歧义时给出下一步——这正是 A2 错误文案承诺的
 * 「到设置页重新选择」的落点。搬家流程（预览 → 确认 → 续跑 / 回滚）整块
 * 在 `MigrateFlow.tsx`，本卡只负责状态呈现与编排。
 */
interface DataLocationCardProps {
  paths: SystemPaths | null;
  pathsError: string | null;
  /** 跨卡错误通道（打开目录等）；迁移自身的反馈留在迁移流程块里 */
  onError: (message: string) => void;
  /** 迁移切换后刷新系统路径（新数据根要如实反映到页面） */
  onReload?: () => void;
  hidden?: boolean;
}

const STATE_LABELS = {
  ok: "settings.dataLocStateOk",
  ambiguous: "settings.dataLocStateAmbiguous",
  uninitialized: "settings.dataLocStateUninitialized",
  unavailable: "settings.dataLocStateUnavailable",
} as const;

const STATE_HINTS = {
  ambiguous: "settings.dataLocStateAmbiguousHint",
  unavailable: "settings.dataLocStateUnavailableHint",
  uninitialized: "settings.dataLocStateUninitializedHint",
  ok: null,
} as const;

export default function DataLocationCard({
  paths,
  pathsError,
  onError,
  onReload,
  hidden = false,
}: DataLocationCardProps) {
  const { t } = useTranslation();
  const diag: DataRootDiagnostic | null = paths?.dataRootDiagnostic ?? null;

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <HardDrive size={16} className="text-primary" /> {t("settings.dataLocTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.dataLocDesc")}
      </p>

      {pathsError ? (
        <p className="text-[0.6875rem] text-destructive">
          {t("settings.pathsFailed", { error: pathsError })}
        </p>
      ) : !paths || !diag ? (
        <Skeleton className="h-12 w-full" />
      ) : (
        <div className="space-y-2">
          <p className="break-all text-[0.6875rem] text-muted-foreground">
            {t("settings.dataRoot")}
            <span className="font-mono text-muted-foreground">{paths.dataRoot}</span>
          </p>
          {/* 来源与遮蔽（B4 整改 D）：spec §五 承诺「展示当前根与来源」——
              诊断对象已有 source/shadowed_by，此前只在类型里、没上屏 */}
          <p className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-muted-foreground">
            <span className="font-mono">
              {t("settings.dataLocSource", { source: diag.source })}
            </span>
            {diag.persisted_selection?.shadowed_by === "env" && (
              <Badge variant="secondary">
                {t("settings.dataLocShadowedByEnv")}
              </Badge>
            )}
          </p>
          <p className="flex flex-wrap items-center gap-2">
            <Badge
              variant={diag.state === "unavailable" ? "destructive" : "outline"}
            >
              {t(STATE_LABELS[diag.state])}
            </Badge>
            <Badge variant="outline">
              {paths.mode === "portable"
                ? t("settings.modePortable")
                : t("settings.modeUser")}
            </Badge>
            <span className="text-[0.6875rem] leading-relaxed text-muted-foreground">
              {paths.mode === "portable"
                ? t("settings.modePortableHint")
                : t("settings.modeUserHint")}
            </span>
            {diag.migration_state !== "idle" && (
              <Badge variant="secondary">
                {t("settings.dataLocMigrationBanner", { phase: diag.migration_state })}
              </Badge>
            )}
          </p>
          {(() => {
            const hintKey = STATE_HINTS[diag.state];
            return hintKey ? (
              <p className="text-[0.6875rem] leading-relaxed text-muted-foreground">
                {t(hintKey)}
              </p>
            ) : null;
          })()}
          {diag.state === "ambiguous" && diag.legacy_candidates.length > 0 && (
            <ul className="space-y-0.5">
              {diag.legacy_candidates.map((candidate) => (
                <li
                  key={candidate.path}
                  className="break-all font-mono text-[0.6875rem] text-muted-foreground"
                >
                  · {candidate.path}
                  {candidate.has_workspace ? " ✓" : ""}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* 迁移流程整块在 MigrateFlow：诊断读不到（后端过旧）时不渲染，不让老后端炸新界面 */}
      {diag && (
        <MigrateFlow migrationInFlight={diag.migration_state !== "idle"} onReload={onReload} />
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          onClick={() => api.openFolder("dataRoot").catch((e: Error) => onError(e.message))}
        >
          <FolderOpen size={15} /> {t("settings.openDataRoot")}
        </Button>
      </div>
    </Card>
  );
}
