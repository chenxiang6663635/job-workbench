// 变更时间线（2026-09-21 从 Applications.tsx 拆出）：投递详情展开区里的只读时间线。
// 拆出的理由：Applications.tsx 是登记过水位的存量文件（只许变小），而它是文件里
// 唯一的内联组件——整体搬走零耦合（也是 H-2「水位拆分」切口的先手）。
import { useTranslation } from "react-i18next";

import type { HistoryEntry } from "../api";

export default function HistoryTimeline({ entries }: { entries: HistoryEntry[] }) {
  const { t } = useTranslation();
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">{t("app.noHistory")}</p>;
  }
  return (
    <div className="space-y-0">
      {entries.map((e, i) => {
        const isStage = e.字段 === "当前阶段" || e.字段 === "创建";
        return (
          <div key={i} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                  isStage ? "bg-primary" : "bg-muted-foreground/50"
                }`}
              />
              {i !== entries.length - 1 && (
                <span className="w-px flex-1 bg-border" />
              )}
            </div>
            <div className="pb-3">
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-muted-foreground">{e.时间}</span>
                <span className="rounded bg-secondary/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                  {e.字段}
                </span>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                <span className="text-muted-foreground">{e.原值 || t("app.emptyValue")}</span>
                <span className="mx-1 text-muted-foreground">→</span>
                {e.新值 || t("app.emptyValue")}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
