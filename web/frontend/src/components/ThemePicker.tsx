import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Palette } from "lucide-react";
import { Card, CardHeader, CardTitle } from "./ui/card";
import { cn } from "../lib/utils";
import { SYSTEM_ID, THEMES, getThemeChoice, setThemeChoice } from "../lib/theme";

// 设置页「外观」卡（批 4）：主题选择。
// - 色块预览取各自官方色板；主题真名不翻译（社区惯例），system 项走 i18n。
// - 选择即生效（applyTheme 只改根属性）+ localStorage 持久化（设备级偏好）。
export default function ThemePicker() {
  const { t } = useTranslation();
  const [choice, setChoice] = useState(getThemeChoice());

  const onPick = (id: string) => {
    setChoice(id);
    setThemeChoice(id);
  };

  return (
    <Card className="space-y-4 p-5">
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Palette size={16} className="text-primary" /> {t("settings.themeTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.themeDesc")}
      </p>

      <div
        className="grid grid-cols-2 gap-2"
        role="radiogroup"
        aria-label={t("settings.themeTitle")}
      >
        {THEMES.map((item) => {
          const active = choice === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onPick(item.id)}
              className={cn(
                "flex cursor-pointer items-center gap-2 rounded-lg border p-2 text-left",
                "transition-colors duration-150",
                active
                  ? "border-primary/60 bg-primary/10"
                  : "border-border bg-surface-1 hover:border-primary/30"
              )}
            >
              <span
                className="flex h-6 w-9 shrink-0 overflow-hidden rounded-md border border-border"
                aria-hidden="true"
              >
                {item.swatch.map((color, i) => (
                  <span key={i} className="h-full flex-1" style={{ background: color }} />
                ))}
              </span>
              <span className="truncate text-xs text-foreground">
                {item.id === SYSTEM_ID ? t("settings.themeSystem") : item.label}
              </span>
            </button>
          );
        })}
      </div>
    </Card>
  );
}
