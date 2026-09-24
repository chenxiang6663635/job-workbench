import { useTranslation } from "react-i18next";
import { RotateCcw, SlidersHorizontal } from "lucide-react";

import type { SettingsEffect, SettingsEntry } from "../../lib/settingsRegistry";
import { cn } from "../../lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle } from "../ui/card";

/**
 * 「外观与偏好」状态卡（笔 4）：把"我改过什么、怎么退回去、什么时候生效"摆在一张卡里。
 *
 * 为什么这张卡值得存在：这几项偏好存在**本机**（localStorage / 主进程），不随工作区导出，
 * 也不进任何备份——用户一年后根本无从回答"我改过什么"。此前唯一的退路是清 localStorage。
 *
 * 被改过的项排在前面并打标；每项旁边写明生效方式（改了没反应时，第一句该问的是"它是即时
 * 生效还是要保存"）。没有回退路径的项不给按钮，而不是给一个点了没用的按钮。
 */
interface PreferenceStatusCardProps {
  entries: SettingsEntry[];
  onReset: (entry: SettingsEntry) => void;
  onResetAll: () => void;
  hidden?: boolean;
}

const EFFECT_KEYS: Record<SettingsEffect, string> = {
  instant: "settings.effectInstant",
  save: "settings.effectSave",
  restart: "settings.effectRestart",
};

export default function PreferenceStatusCard({
  entries,
  onReset,
  onResetAll,
  hidden = false,
}: PreferenceStatusCardProps) {
  const { t } = useTranslation();
  if (entries.length === 0) return null;

  const modified = entries.filter((entry) => entry.modified);
  const ordered = [...modified, ...entries.filter((entry) => !entry.modified)];

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <SlidersHorizontal size={16} className="text-primary" /> {t("settings.statusTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.statusDesc")}
      </p>

      <div className="space-y-1.5">
        {ordered.map((entry) => (
          <div
            key={entry.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-background/40 px-3 py-2"
          >
            <div className="min-w-0 space-y-0.5">
              <p className="flex items-center gap-1.5 text-xs text-foreground">
                {t(entry.labelKey)}
                {entry.modified && (
                  <Badge variant="outline" className="px-1 py-0 text-[10px]">
                    {t("settings.statusModified")}
                  </Badge>
                )}
              </p>
              <p className="truncate text-[11px] text-muted-foreground">
                {entry.value} · {t(EFFECT_KEYS[entry.effect])}
              </p>
            </div>
            {entry.modified && entry.reset && (
              <Button
                variant="outline"
                className="h-7 shrink-0 px-2.5 text-[11px]"
                onClick={() => onReset(entry)}
              >
                <RotateCcw size={12} /> {t("settings.statusResetOne")}
              </Button>
            )}
          </div>
        ))}
      </div>

      {modified.length > 1 && (
        <div className="border-t border-border pt-3">
          <Button variant="outline" className="h-7 px-2.5 text-[11px]" onClick={onResetAll}>
            <RotateCcw size={12} /> {t("settings.statusResetAll", { n: modified.length })}
          </Button>
        </div>
      )}
    </Card>
  );
}
