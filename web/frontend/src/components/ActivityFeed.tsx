import { Activity } from "lucide-react";
import { Card } from "./ui/card";
import { EmptyState } from "./ui/empty";
import { useTranslation } from "react-i18next";

// 最近动作（批 4）：Linear / GitHub 的活动流模式——用**既有时间线数据**填充看板，
// 让「最近发生了什么」一屏可见，而不是翻追踪表。数据来自后端 recentActivity
// （history.csv 时间线最近 12 条，附公司名；排序在服务端完成）。
// 2026-09-17：空态并入 EmptyState 原语（此前是一行灰字）。

export interface ActivityEntry {
  time: string;
  id: string;
  company: string;
  field: string;
  old: string;
  new: string;
}

export default function ActivityFeed({ entries }: { entries: ActivityEntry[] }) {
  const { t } = useTranslation();
  return (
    <Card className="space-y-3 p-5">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <Activity size={14} className="text-primary" /> {t("dash.activityTitle")}
      </h2>
      {entries.length === 0 ? (
        <EmptyState title={t("dash.activityEmpty")} compact />
      ) : (
        <ol className="space-y-2.5">
          {entries.map((entry, index) => (
            <li
              key={`${entry.time}-${entry.id}-${index}`}
              className="flex items-start gap-2.5 text-xs"
            >
              <span
                className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-foreground">
                  <span className="font-medium">{entry.company || entry.id}</span>
                  <span className="mx-1 text-muted-foreground">·</span>
                  <span className="text-muted-foreground">{entry.field}</span>
                </p>
                <p className="truncate text-muted-foreground">
                  {entry.old ? `${entry.old} → ` : ""}
                  {entry.new}
                </p>
              </div>
              <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground">
                {entry.time.slice(0, 16)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
