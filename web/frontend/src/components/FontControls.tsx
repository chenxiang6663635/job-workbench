import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useUndoableAction } from "../hooks/useUndoableAction";
import {
  FONTS,
  FONT_SIZE_DEFAULT,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  FONT_SIZE_STEP,
  MONOS,
  NUMERICS,
  getFontChoice,
  getFontSizeChoice,
  getMonoChoice,
  getNumericChoice,
  setFontChoice,
  setFontSizeChoice,
  setMonoChoice,
  setNumericChoice,
} from "../lib/theme";
import { Button } from "./ui/button";
import { Num } from "./ui/number";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import UndoBar from "./UndoBar";

/**
 * 外观卡里的三槽字体 + 界面字号（2026-09-23 从 ThemePicker 拆出）。
 *
 * 拆出来的直接原因是规模闸门：给 ThemePicker 加 `version` / `hidden` 之后它越过 300 行，
 * 按纪律只能拆、不能登记（水位是只许变小的存量债）。顺着职责切也自然——主题选择是"挑一套
 * 现成的"，字体与字号是"在既定主题里调排版"，两者的状态与回退机制本来就不同（字号那一路
 * 走 5 秒撤销条）。
 *
 * 只改 html[data-*] 属性：字体栈本体在 index.css 的变量里；字体真名不翻译（社区惯例），
 * system / serif / follow 这类"跟随"项走 i18n。
 */
export default function FontControls({ version = 0 }: { version?: number }) {
  const { t } = useTranslation();
  const [font, setFont] = useState(getFontChoice());
  const [mono, setMono] = useState(getMonoChoice());
  const [numeric, setNumeric] = useState(getNumericChoice());
  const [fontSize, setFontSize] = useState(getFontSizeChoice());
  // 字号"还原默认"走撤销条（笔 1 的统一机制）：即时生效 + 5 秒内可撤销
  const { pending, run, undo } = useUndoableAction();

  // 外部还原（状态卡里的「还原默认」）之后对齐真值源；同步而不是重挂载——本组件里有未决的
  // 撤销窗口，重挂载会把它清掉（2026-09-23 首跑 e2e 的教训）
  useEffect(() => {
    setFont(getFontChoice());
    setMono(getMonoChoice());
    setNumeric(getNumericChoice());
    setFontSize(getFontSizeChoice());
  }, [version]);

  return (
    <>
      {/* 字体方案（4g → 2026-09-17 扩到 14 项）：14 项用下拉（按钮排不下两行） */}
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
          <SelectTrigger className="h-8 w-full text-xs" aria-label={t("settings.fontTitle")}>
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
          <SelectTrigger className="h-8 w-full text-xs" aria-label={t("settings.fontMonoTitle")}>
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

        {/* 数字字体（第三槽，批 4.6）：只影响 --font-numeric-*——数值（KPI / 计数 / 天数 / 百分比） */}
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
          <SelectTrigger className="h-8 w-full text-xs" aria-label={t("settings.fontNumericTitle")}>
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

      {/* 界面字号（#4 → 2026-09-17 改连续滑块）：根字号 80–150%（步进 5），rem 全链等比
          缩放、与桌面全局缩放解耦。用原生 range（跨浏览器最稳、键盘/方向键天然可用） */}
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
          <span className="text-base font-semibold text-muted-foreground" aria-hidden="true">
            A
          </span>
          <Button
            variant="outline"
            size="sm"
            className="h-7 shrink-0 px-2 text-xs"
            disabled={fontSize === FONT_SIZE_DEFAULT}
            onClick={() => {
              // 「还原默认」是典型的后悔药场景：即时生效（视觉立刻变，用户马上看得到），
              // 配 5 秒撤销条。四项判据（单项 / 可见 / 可辨 / 可延迟）全成立 → 给撤销、
              // 不给确认框（两者同时给会让确认框沦为形式）。
              const previous = fontSize;
              setFontSize(FONT_SIZE_DEFAULT);
              setFontSizeChoice(FONT_SIZE_DEFAULT);
              run({
                message: t("settings.fontSizeResetDone", { size: String(FONT_SIZE_DEFAULT) }),
                revert: () => {
                  setFontSize(previous);
                  setFontSizeChoice(previous);
                },
              });
            }}
          >
            {t("settings.fontSizeReset")}
          </Button>
        </div>
      </div>
      {pending ? <UndoBar message={pending.message} onUndo={undo} /> : null}
    </>
  );
}
