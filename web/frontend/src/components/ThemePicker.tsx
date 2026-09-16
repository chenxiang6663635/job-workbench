import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Palette, SlidersHorizontal } from "lucide-react";
import { Card, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Segmented } from "./ui/segmented";
import { cn } from "../lib/utils";
import {
  FONTS,
  SYSTEM_ID,
  getFontChoice,
  getFontSizeChoice,
  getThemeChoice,
  listThemes,
  setFontChoice,
  setFontSizeChoice,
  setThemeChoice,
} from "../lib/theme";
import type { TranslationKey } from "../i18n/locales/zh-CN";
import ThemeEditor from "./ThemeEditor";

// 字号档标签（#4）：key 走 TranslationKey 类型——拼错在编译期报（与 TABS 同一约定）
const FONT_SIZE_OPTIONS: { value: string; labelKey: TranslationKey }[] = [
  { value: "sm", labelKey: "settings.fontSizeSm" },
  { value: "base", labelKey: "settings.fontSizeBase" },
  { value: "lg", labelKey: "settings.fontSizeLg" },
  { value: "xl", labelKey: "settings.fontSizeXl" },
];

// 设置页「外观」卡（批 4）：主题选择 + 自定义主题入口。
// - 色块预览取各自色板；主题真名不翻译（社区惯例），system 项走 i18n。
// - 选择即生效（applyTheme 只改根属性）+ localStorage 持久化（设备级偏好）。
export default function ThemePicker() {
  const { t } = useTranslation();
  const [choice, setChoice] = useState(getThemeChoice());
  const [themes, setThemes] = useState(listThemes());
  const [editing, setEditing] = useState(false);
  const [font, setFont] = useState(getFontChoice());
  const [fontSize, setFontSize] = useState(getFontSizeChoice());

  const onPick = (id: string) => {
    setChoice(id);
    setThemeChoice(id);
  };

  const refresh = () => {
    setThemes(listThemes());
    setChoice(getThemeChoice());
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

      {/* 字体方案（4g）：只改 html[data-font]，栈本体在 index.css 的变量里 */}
      <div className="border-t border-border pt-3">
        <p className="mb-2 text-xs font-medium text-foreground">
          {t("settings.fontTitle")}
        </p>
        <div
          className="flex flex-wrap gap-2"
          role="radiogroup"
          aria-label={t("settings.fontTitle")}
        >
          {FONTS.map((item) => (
            <Button
              key={item.id}
              variant={font === item.id ? "default" : "outline"}
              size="sm"
              className="h-7 px-3 text-xs"
              aria-pressed={font === item.id}
              onClick={() => {
                setFont(item.id);
                setFontChoice(item.id);
              }}
            >
              {item.id === "system" ? t("settings.fontSystem") : item.label}
            </Button>
          ))}
        </div>
      </div>

      {/* 界面字号（#4）：四档根字号缩放（rem 全链）——与桌面全局缩放解耦，
          浏览器端同样生效；方向键由原生 radio（Segmented）天然支持 */}
      <div className="border-t border-border pt-3">
        <p className="mb-2 text-xs font-medium text-foreground">
          {t("settings.fontSizeTitle")}
        </p>
        <Segmented
          value={fontSize}
          onChange={(next) => {
            setFontSize(next);
            setFontSizeChoice(next);
          }}
          options={FONT_SIZE_OPTIONS.map((item) => ({
            value: item.value,
            label: t(item.labelKey),
          }))}
          ariaLabel={t("settings.fontSizeTitle")}
        />
      </div>
    </Card>
  );
}
