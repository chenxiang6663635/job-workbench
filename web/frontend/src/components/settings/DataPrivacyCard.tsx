import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Archive, Download, FolderOpen, ShieldCheck, Stethoscope } from "lucide-react";

import { api, type SystemPaths } from "../../api";
import { diagnosticsUrl } from "../../lib/diagnostics";
import { currentWorkspace } from "../../lib/http";
import type { SnapshotInfo } from "../../lib/domainTypes";
import { listSnapshots } from "../../lib/snapshotApi";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle } from "../ui/card";
import { Skeleton } from "../ui/skeleton";
import SnapshotList from "./SnapshotList";

/**
 * 「数据与隐私」卡（2026-09-23 从 pages/Settings.tsx 拆出，收口批 笔 2）。
 *
 * 拆出来有两个理由，都不是审美：
 * 1. `Settings.tsx` 是登记过水位（693 行，只许变小）的存量文件——本笔要在这张卡里加
 *    「快照列表 + 演练 + 还原」，不搬走一段就必然红；
 * 2. 这张卡现在管的是**不可逆的那一类事**（导出、备份、还原），与「填个 API key」
 *    不是同一种风险级别，单独一个文件才谈得上单独读一遍。
 *
 * 数据流向：`paths` 由页面持有（「数据位置」与「关于」两张卡也在用），本卡只负责
 * 触发重取；快照清单是本卡自己的状态（只有这里用得到）。
 */
interface DataPrivacyCardProps {
  paths: SystemPaths | null;
  pathsError: string | null;
  /** 重取 /api/system/paths（备份或还原之后「上次备份」会变） */
  onReload: () => void;
  onError: (message: string) => void;
  /** 设置页的搜索/分组过滤：隐藏时保留挂载（与"没这张卡"不同，状态不丢） */
  hidden?: boolean;
}

export default function DataPrivacyCard({
  paths,
  pathsError,
  onReload,
  onError,
  hidden = false,
}: DataPrivacyCardProps) {
  const { t } = useTranslation();
  const [backing, setBacking] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotInfo[]>([]);
  const [snapshotsLoading, setSnapshotsLoading] = useState(true);

  const loadSnapshots = () => {
    setSnapshotsLoading(true);
    listSnapshots()
      .then((r) => setSnapshots(r.snapshots))
      .catch((e: Error) => onError(e.message))
      .finally(() => setSnapshotsLoading(false));
  };

  // 只在挂载时取一次：onError 是父级的 setState 包装，每次渲染都是新引用，进依赖
  // 数组等于每次渲染都重取一遍清单（与 pages/Settings.tsx 的 load/loadImap 同款处理）
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(loadSnapshots, []);

  const reloadAll = () => {
    onReload();
    loadSnapshots();
  };

  const backup = () => {
    setInfo(null);
    setBacking(true);
    api
      .backupWorkspace()
      .then((r) => {
        setInfo(
          t("settings.backupDone", {
            files: r.files,
            size: (r.size / 1024).toFixed(0),
            kept: r.kept,
            removed: r.removed,
          })
        );
        reloadAll();
      })
      .catch((e: Error) => onError(e.message))
      .finally(() => setBacking(false));
  };

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
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
          <a href={api.exportUrl()} onClick={() => setInfo(t("settings.exportNotice"))}>
            <Download size={15} /> {t("settings.exportZip")}
          </a>
        </Button>
        <Button variant="outline" onClick={backup} disabled={backing}>
          <Archive size={15} /> {backing ? t("settings.backingup") : t("settings.backupNow")}
        </Button>
        <Button
          variant="outline"
          onClick={() => api.openFolder("workspace").catch((e: Error) => onError(e.message))}
        >
          <FolderOpen size={15} /> {t("settings.openDataDir")}
        </Button>
        {/* 诊断包是给"出问题要报障"用的：链接直下，不经 requestJson（浏览器下载） */}
        <Button asChild variant="outline">
          <a href={diagnosticsUrl(currentWorkspace)} title={t("settings.diagnosticsDesc")}>
            <Stethoscope size={15} /> {t("settings.diagnostics")}
          </a>
        </Button>
      </div>

      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {t("settings.diagnosticsDesc")}
      </p>

      {info && (
        <p className="rounded-lg border border-border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
          {info}
        </p>
      )}

      <div className="space-y-2 border-t border-border pt-3">
        <SnapshotList
          snapshots={snapshots}
          loading={snapshotsLoading}
          onRestored={reloadAll}
          onError={onError}
        />
      </div>

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
        <p className="pt-1 text-muted-foreground">{t("settings.snapshotNote")}</p>
      </div>
    </Card>
  );
}
