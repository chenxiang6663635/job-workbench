import { useTranslation } from "react-i18next";
import { Filter, Search } from "lucide-react";

import { SETTINGS_GROUPS, type SettingsGroupId } from "../../lib/settingsRegistry";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

/**
 * 设置页的「找得到」工具条（笔 4）：过滤搜索 + 分组 + 只看已修改。
 *
 * 结构化记号只取 `@modified` 一条（VS Code 那套 @tag / @id 的最小集）——设置项约三十条，
 * 引入完整过滤器语法是给自己加维护面。搜索词直接写进同一个输入框，不另开面板。
 */
interface SettingsToolsProps {
  query: string;
  onQueryChange: (value: string) => void;
  group: SettingsGroupId | "all";
  onGroupChange: (value: SettingsGroupId | "all") => void;
  modified: number;
}

export default function SettingsTools({
  query,
  onQueryChange,
  group,
  onGroupChange,
  modified,
}: SettingsToolsProps) {
  const { t } = useTranslation();
  const modifiedOnly = query.toLowerCase().includes("@modified");

  return (
    <div className="space-y-2 rounded-xl border border-border bg-card/60 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Search size={14} className="shrink-0 text-muted-foreground" aria-hidden="true" />
        <Input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={t("settings.toolsSearchPlaceholder")}
          aria-label={t("settings.toolsSearchLabel")}
          className="h-8 min-w-[12rem] flex-1 text-xs"
        />
        <Button
          variant={modifiedOnly ? "default" : "outline"}
          className="h-8 shrink-0 px-2.5 text-[11px]"
          aria-pressed={modifiedOnly}
          onClick={() => onQueryChange(modifiedOnly ? "" : "@modified")}
        >
          <Filter size={12} /> {t("settings.toolsModifiedOnly")}
          {modified > 0 && (
            <Badge variant="outline" className="ml-1 px-1 py-0 text-[10px]">
              {modified}
            </Badge>
          )}
        </Button>
      </div>

      {/* 分组：Material 的阈值判据是十五项以上就该有子屏入口——这里九个分区先按四个分组收 */} 
      <div
        className="flex flex-wrap items-center gap-1.5"
        role="group"
        aria-label={t("settings.toolsGroups")}
      >
        <Button
          size="sm"
          variant={group === "all" ? "secondary" : "ghost"}
          className="h-7 px-2.5 text-[11px]"
          aria-pressed={group === "all"}
          onClick={() => onGroupChange("all")}
        >
          {t("settings.toolsAll")}
        </Button>
        {SETTINGS_GROUPS.map((item) => (
          <Button
            key={item.id}
            size="sm"
            variant={group === item.id ? "secondary" : "ghost"}
            className="h-7 px-2.5 text-[11px]"
            aria-pressed={group === item.id}
            onClick={() => onGroupChange(item.id)}
          >
            {t(item.labelKey)}
          </Button>
        ))}
      </div>
    </div>
  );
}
