import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Palette, SlidersHorizontal } from "lucide-react";
import { Card, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { cn } from "../lib/utils";
import { Num } from "./ui/number";
import {
  FONTS,
  FONT_SIZE_DEFAULT,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  FONT_SIZE_STEP,
  MONOS,
  NUMERICS,
  SYSTEM_ID,
  getFontChoice,
  getFontSizeChoice,
  getMonoChoice,
  getNumericChoice,
  getThemeChoice,
  listThemes,
  setFontChoice,
  setFontSizeChoice,
  setMonoChoice,
  setNumericChoice,
  setThemeChoice,
} from "../lib/theme";
import ThemeEditor from "./ThemeEditor";

// 设置页「外观」卡（批 4）：主题选择 + 自定义主题入口。
// - 色块预览取各自色板；主题真名不翻译（社区惯例），system 项走 i18n。
// - 选择即生效（applyTheme 只改根属性）+ localStorage 持久化（设备级偏好）。
export default function ThemePicker() {
  const { t } = useTranslation();
  const [choice, setChoice] = useState(getThemeChoice());
  const [themes, setThemes] = useState(listThemes());
  const [editing, setEditing] = useState(false);
  const [font, setFont] = useState(getFontChoice());
  const [mono, setMono] = useState(getMonoChoice());
  const [numeric, setNumeric] = useState(getNumericChoice());
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

      {/* 字体方案（4g → 2026-09-17 扩到 14 项）：只改 html[data-font]，
          栈本体在 index.css 的变量里；14 项用下拉（按钮排不下两行）。
          字体真名不翻译（社区惯例），system / serif 两项走 i18n */}
      <div className="border-t border-border pt-3">
        <p className="mb-2 text-xs font-medium text-foreground">
          {t("settings.fontTitle")}
        </p>
        <Select
          value={font}
          onValueChange={(next) => {
            setFont(next);
            setFontChoice(next);
          }}
        >
          <SelectTrigger
            className="h-8 w-full text-xs"
            aria-label={t("settings.fontTitle")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FONTS.map((item) => (
              <SelectItem key={item.id} value={item.id} className="text-xs">
                {item.id === "system"
                  ? t("settings.fontSystem")
                  : item.id === "serif"
                    ? t("settings.fontSerif")
                    : item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 等宽字体（独立槽）：只影响 --font-mono-*（代码、编号、日期） */}
        <p className="mb-2 mt-4 text-xs font-medium text-foreground">
          {t("settings.fontMonoTitle")}
        </p>
        <Select
          value={mono}
          onValueChange={(next) => {
            setMono(next);
            setMonoChoice(next);
          }}
        >
          <SelectTrigger
            className="h-8 w-full text-xs"
            aria-label={t("settings.fontMonoTitle")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MONOS.map((item) => (
              <SelectItem key={item.id} value={item.id} className="text-xs">
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 数字字体（第三槽，批 4.6）：只影响 --font-numeric-*——数值（KPI /
            计数 / 天数 / 百分比）；"follow" 项走 i18n，字体真名不翻译 */}
        <p className="mb-2 mt-4 text-xs font-medium text-foreground">
          {t("settings.fontNumericTitle")}
        </p>
        <Select
          value={numeric}
          onValueChange={(next) => {
            setNumeric(next);
            setNumericChoice(next);
          }}
        >
          <SelectTrigger
            className="h-8 w-full text-xs"
            aria-label={t("settings.fontNumericTitle")}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {NUMERICS.map((item) => (
              <SelectItem key={item.id} value={item.id} className="text-xs">
                {item.id === "follow" ? t("settings.fontFollow") : item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 界面字号（#4 → 2026-09-17 改连续滑块）：根字号 80–150%（步进 5），
          rem 全链等比缩放、与桌面全局缩放解耦。用原生 range（跨浏览器最稳、
          键盘/方向键天然可用），accent-color 跟随主题主色 */}
      <div className="border-t border-border pt-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-medium text-foreground">
            {t("settings.fontSizeTitle")}
          </p>
          <Num muted className="text-xs">
            {fontSize}%
          </Num>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-muted-foreground" aria-hidden="true">
            A
          </span>
          <input
            type="range"
            min={FONT_SIZE_MIN}
            max={FONT_SIZE_MAX}
            step={FONT_SIZE_STEP}
            value={fontSize}
            aria-label={t("settings.fontSizeTitle")}
            onChange={(event) => {
              const next = Number(event.target.value);
              setFontSize(next);
              setFontSizeChoice(next);
            }}
            className="w-full cursor-pointer accent-primary"
          />
          <span
            className="text-base font-semibold text-muted-foreground"
            aria-hidden="true"
          >
            A
          </span>
          <Button
            variant="outline"
            size="sm"
            className="h-7 shrink-0 px-2 text-xs"
            disabled={fontSize === FONT_SIZE_DEFAULT}
            onClick={() => {
              setFontSize(FONT_SIZE_DEFAULT);
              setFontSizeChoice(FONT_SIZE_DEFAULT);
            }}
          >
            {t("settings.fontSizeReset")}
          </Button>
        </div>
      </div>
    </Card>
  );
}
