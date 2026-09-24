import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FlaskConical, RotateCcw } from "lucide-react";

import type { SnapshotInfo, SnapshotPreview } from "../../lib/domainTypes";
import { previewSnapshot, restoreSnapshot } from "../../lib/snapshotApi";
import {
  canRestore,
  drillBadges,
  formatBytes,
  formatSnapshotTime,
} from "../../lib/snapshotMeta";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Skeleton } from "../ui/skeleton";
import ConfirmDangerDialog from "../ConfirmDangerDialog";

/**
 * 快照列表 + 演练 + 还原（首发前收口批 笔 2）。
 *
 * 交互上只有一条主张：**先演练、再动手**。点「还原」不是直接弹确认框，而是先跑一次
 * 只读演练，把「会覆盖几个 / 会补齐几个 / 快照外有几个保留不动」摆进确认框的正文里——
 * 用户按下的那一刻，屏幕上的字就是他即将付出的代价。
 *
 * 分级用 `phrase` 档（要照打一个词），不是 `confirm` 档：这是本项目里唯一一处"会覆盖
 * 现有内容"的动作，本仓 `ConfirmDangerDialog` 的分档说明也正是这么举例的（"会连带
 * 丢数据的，要求照打一句确认词"）。回滚快照由后端在还原前自动落，但那是兜底，不是
 * 让用户少看一眼的理由。
 */
interface SnapshotListProps {
  snapshots: SnapshotInfo[];
  loading: boolean;
  /** 还原成功后刷新清单与「上次备份」信息 */
  onRestored: () => void;
  onError: (message: string) => void;
}

/** 演练徽章 → 文案 key。写成常量表而不是嵌套三元：key 是静态的，扫描器与人都读得懂。 */
const DRILL_LABELS = {
  overwrite: "settings.snapshotOverwrite",
  add: "settings.snapshotAdd",
  same: "settings.snapshotSame",
} as const;

export default function SnapshotList({
  snapshots,
  loading,
  onRestored,
  onError,
}: SnapshotListProps) {
  const { t } = useTranslation();
  const [drill, setDrill] = useState<{ name: string; preview: SnapshotPreview } | null>(null);
  const [drilling, setDrilling] = useState<string | null>(null);
  const [target, setTarget] = useState<{ name: string; preview: SnapshotPreview } | null>(null);
  const [preparing, setPreparing] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  const runDrill = (name: string) => {
    setDrilling(name);
    setDone(null);
    previewSnapshot(name)
      .then((preview) => setDrill({ name, preview }))
      .catch((e: Error) => onError(e.message))
      .finally(() => setDrilling(null));
  };

  /**
   * 还原入口：先演练一次（拿到差异），再把它带进确认框。
   *
   * 差异为 0 时**不打开对话框**，只把演练结果留在页面上并说明原因——让用户点进确认框、
   * 打完确认词，最后得到一句"其实没有变化"，是把判断推给人（见 lib/snapshotMeta 的
   * `canRestore`）。
   */
  const openRestore = (name: string) => {
    setPreparing(name);
    setDone(null);
    previewSnapshot(name)
      .then((preview) => {
        setDrill({ name, preview });
        if (canRestore(preview)) setTarget({ name, preview });
      })
      .catch((e: Error) => onError(e.message))
      .finally(() => setPreparing(null));
  };

  const doRestore = () => {
    if (!target) return;
    setRestoring(true);
    restoreSnapshot(target.name)
      .then((result) => {
        setTarget(null);
        setDone(
          t("settings.snapshotRestoreDone", {
            restored: result.restored,
            added: result.added,
            same: result.same,
            rollback: result.preRestoreSnapshot,
          })
        );
        onRestored();
      })
      .catch((e: Error) => onError(e.message))
      .finally(() => setRestoring(false));
  };

  if (loading) return <Skeleton className="h-12 w-full" />;

  if (snapshots.length === 0) {
    return (
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {t("settings.snapshotEmpty")}
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-[11px] font-medium text-foreground">
        {t("settings.snapshotListTitle")}
      </p>

      <div className="space-y-1.5">
        {snapshots.map((item) => (
          <div
            key={item.name}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background/40 px-3 py-2"
          >
            <div className="min-w-0 space-y-0.5">
              <p className="truncate font-mono text-[11px] text-foreground">{item.name}</p>
              <p className="text-[11px] text-muted-foreground">
                {formatSnapshotTime(item.mtime)}
                {" · "}
                {formatBytes(item.size)}
                {item.files !== null &&
                  ` · ${t("settings.snapshotFileCount", { n: item.files })}`}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button
                variant="outline"
                className="h-7 px-2.5 text-[11px]"
                disabled={drilling !== null || preparing !== null}
                onClick={() => runDrill(item.name)}
              >
                <FlaskConical size={12} />
                {drilling === item.name
                  ? t("settings.snapshotDrilling")
                  : t("settings.snapshotDrill")}
              </Button>
              <Button
                variant="outline"
                className="h-7 px-2.5 text-[11px]"
                disabled={drilling !== null || preparing !== null}
                onClick={() => openRestore(item.name)}
              >
                <RotateCcw size={12} />
                {preparing === item.name
                  ? t("settings.snapshotPreparing")
                  : t("settings.snapshotRestore")}
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* 演练结果：差异摆在动手之前。零写入由后端保证（见 tests/test_snapshot_restore.py） */}
      {drill && (
        <div className="space-y-1.5 rounded-lg border border-border bg-background/60 px-3 py-2">
          <p className="truncate text-[11px] text-muted-foreground">
            {t("settings.snapshotDrillFor", { name: drill.name })}
          </p>
          <div className="flex flex-wrap items-center gap-1.5">
            {drillBadges(drill.preview).map((badge) => (
              <Badge key={badge.key} variant="outline" className="text-[11px]">
                {t(DRILL_LABELS[badge.key], { n: badge.count })}
              </Badge>
            ))}
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            {t("settings.snapshotKept", { n: drill.preview.notInSnapshot })}
          </p>
          {drill.preview.keptExamples.length > 0 && (
            <p className="break-all text-[11px] text-muted-foreground">
              {t("settings.snapshotKeptExamples", {
                list: drill.preview.keptExamples.join(" / "),
              })}
            </p>
          )}
          {!canRestore(drill.preview) && (
            <p className="text-[11px] text-muted-foreground">
              {t("settings.snapshotNothingToDo")}
            </p>
          )}
          <p className="text-[11px] text-muted-foreground">{t("settings.snapshotDrillHint")}</p>
        </div>
      )}

      {done && (
        <p className="rounded-lg border border-success/30 bg-success/10 px-3 py-2 text-xs text-muted-foreground">
          {done}
        </p>
      )}

      <ConfirmDangerDialog
        open={target !== null}
        level="phrase"
        title={t("settings.snapshotRestoreTitle")}
        description={
          target
            ? t("settings.snapshotRestoreDesc", {
                overwrite: target.preview.overwrite,
                add: target.preview.add,
                kept: target.preview.notInSnapshot,
              })
            : ""
        }
        confirmLabel={t("settings.snapshotRestoreConfirm")}
        challenge={t("settings.snapshotRestoreWord")}
        challengeLabel={t("settings.snapshotChallengeLabel", {
          word: t("settings.snapshotRestoreWord"),
        })}
        busy={restoring}
        onCancel={() => setTarget(null)}
        onConfirm={doRestore}
      />
    </div>
  );
}
