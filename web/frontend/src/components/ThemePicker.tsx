import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Palette, SlidersHorizontal } from "lucide-react";

import { cn } from "../lib/utils";
import { SYSTEM_ID, getThemeChoice, listThemes, setThemeChoice } from "../lib/theme";
import { Button } from "./ui/button";
import { Card, CardHeader, CardTitle } from "./ui/card";
import FontControls from "./FontControls";
import ThemeEditor from "./ThemeEditor";

// 设置页「外观」卡（批 4）：主题选择 + 自定义主题入口 + 字体与字号（后两块在 FontControls）。
// - 色块预览取各自色板；主题真名不翻译（社区惯例），system 项走 i18n。
// - 选择即生效（applyTheme 只改根属性）+ localStorage 持久化（设备级偏好）。
export default function ThemePicker({
  hidden = false,
  version = 0,
}: {
  hidden?: boolean;
  /**
   * 外部（设置页的「外观与偏好」状态卡）改了偏好之后递增的版本号。
   *
   * 这里**刻意只同步状态、不靠 key 重挂载**：本卡里有未决的撤销窗口（字号还原的 5 秒）
   * 与主题编辑器草稿，重挂载会把它们一并清掉——2026-09-23 首跑 e2e 就是这么红的
   * （三条 ux 用例：撤消条消失、确认框与编辑器状态被重置）。
   */
  version?: number;
}) {
  const { t } = useTranslation();
  const [choice, setChoice] = useState(getThemeChoice());
  const [themes, setThemes] = useState(listThemes());
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    setThemes(listThemes());
    setChoice(getThemeChoice());
  }, [version]);

  const onPick = (id: string) => {
    setChoice(id);
    setThemeChoice(id);
  };

  const refresh = () => {
    setThemes(listThemes());
    setChoice(getThemeChoice());
  };

  return (
    <Card className={cn("space-y-4 p-5", hidden && "hidden")}>
      <CardHeader className="p-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Palette size={16} className="text-primary" /> {t("settings.themeTitle")}
        </CardTitle>
      </CardHeader>

      <p className="text-xs leading-relaxed text-muted-foreground">
        {t("settings.themeDesc")}
      </p>

      {/* 三列（#4）：双列时 10 套主题把卡片撑得远高于同排邻居——设置页两列
          瀑布流的参差感主要来自这里；三列把外观卡压回常规高度 */}
      <div
        className="grid grid-cols-2 gap-2 sm:grid-cols-3"
        role="radiogroup"
        aria-label={t("settings.themeTitle")}
      >
        {themes.map((item) => {
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

      {/* 自定义主题：编辑器 MVP——从当前主题的全部变量出发，只调关键色 */}
      <div className="border-t border-border pt-3">
        <Button
          variant="outline"
          size="sm"
          onClick={() => setEditing((prev) => !prev)}
          aria-expanded={editing}
        >
          <SlidersHorizontal size={13} className="mr-1" />
          {editing ? t("settings.themeEditorClose") : t("settings.themeCustom")}
        </Button>
      </div>

      {editing && <ThemeEditor onSaved={refresh} />}

      <FontControls version={version} />
    </Card>
  );
}
