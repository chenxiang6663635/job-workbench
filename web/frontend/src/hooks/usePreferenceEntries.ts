import { useCallback, useEffect, useState } from "react";

import i18n, { LANGS, systemLang } from "../i18n";

/** i18next 可能给出 `en-US` 这类变体；与 LANGS / systemLang 同一口径归一后再比默认值。 */
function normalizeLang(value: string): string {
  return value.toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}
import {
  DEFAULT_NUMERIC_ID,
  FONTS,
  FONT_SIZE_DEFAULT,
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
} from "../lib/fonts";
import { SYSTEM_ID, getThemeChoice, listThemes, setThemeChoice } from "../lib/theme";
import {
  getPrefs,
  hasDesktopPrefs,
  onZoomChanged,
  setReminders,
  setZoomLevel,
  type PrefsSnapshot,
} from "../lib/prefs";
import {
  buildPreferenceEntries,
  type PreferenceSources,
  type SettingsEntry,
} from "../lib/settingsRegistry";

/**
 * 设置页「外观与偏好」的真值源适配层（笔 4）。
 *
 * 这一层是刻意薄的：判定全在 `lib/settingsRegistry`（纯函数、有单测），这里只做两件
 * 纯 IO 的事——读四个真值源（localStorage / i18n / 主进程偏好）与把还原动作接上。
 *
 * `version` 是给调用方的重挂载信号：还原主题之类会改到别的卡片自己的内部状态（外观卡把
 * 当前主题放在 useState 里），只刷新数据不会让它重画——Settings.tsx 用它给 ThemePicker 加 key。
 */
export function usePreferenceEntries(): {
  entries: SettingsEntry[];
  refresh: () => void;
  version: number;
} {
  const [version, setVersion] = useState(0);
  const [prefs, setPrefs] = useState<PrefsSnapshot | null>(null);

  const refresh = useCallback(() => setVersion((value) => value + 1), []);

  useEffect(() => {
    let alive = true;
    getPrefs()?.then((snapshot) => {
      if (alive) setPrefs(snapshot);
    });
    return () => {
      alive = false;
    };
  }, [version]);

  // 外观类偏好的**信号就是根元素属性**：主题 / 字体 / 字号 / `<html lang>` 都写在那里。
  // 观察它比给每张卡串一个 onChange 更可靠——将来多一处写属性的入口也不会漏（e2e 首跑
  // 就是红的：点主题只改了 localStorage，状态卡不知道，于是"已改"标记永远不出现）。
  //
  // 两条纪律（批末审查）：① **不观察 `style`**——否则主题编辑器每敲一个色值都换来一次
  // IPC + 全页重渲染（字号改成写 `data-fontsize`，见 lib/fonts.applyFontSize）；
  // ② 值没变就不刷新——同一属性被写回同一个值是常见路径，白白刷一轮没有任何收益。
  // 另：这个 effect 只**读**根属性；谁要是往 version 的副作用里写根属性，就会自激成环。
  useEffect(() => {
    const attrs = ["data-theme", "data-font", "data-mono", "data-numeric", "data-fontsize", "lang"];
    const snapshot = () =>
      attrs.map((name) => `${name}=${document.documentElement.getAttribute(name) ?? ""}`).join("|");
    let last = snapshot();
    const observer = new MutationObserver(() => {
      const next = snapshot();
      if (next === last) return;
      last = next;
      refresh();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: attrs });
    return () => observer.disconnect();
  }, [refresh]);

  // 缩放不走属性（主进程驱动的原生层），走广播——与设置页滑块同一个订阅源
  useEffect(() => onZoomChanged(() => refresh()), [refresh]);

  const labelOf = (options: { id: string; label: string }[], id: string) =>
    options.find((item) => item.id === id)?.label ?? id;

  const currentLang = normalizeLang(i18n.language);
  const themeChoice = getThemeChoice();
  const themeLabel = listThemes().find((item) => item.id === themeChoice)?.label ?? themeChoice;

  const sources: PreferenceSources = {
    theme: {
      value: themeChoice,
      def: SYSTEM_ID,
      display: themeLabel,
      reset: () => {
        setThemeChoice(SYSTEM_ID);
        refresh();
      },
    },
    font: {
      value: getFontChoice(),
      def: FONTS[0].id,
      display: labelOf(FONTS, getFontChoice()),
      reset: () => {
        setFontChoice(FONTS[0].id);
        refresh();
      },
    },
    mono: {
      value: getMonoChoice(),
      def: MONOS[0].id,
      display: labelOf(MONOS, getMonoChoice()),
      reset: () => {
        setMonoChoice(MONOS[0].id);
        refresh();
      },
    },
    numeric: {
      value: getNumericChoice(),
      def: DEFAULT_NUMERIC_ID,
      display: labelOf(NUMERICS, getNumericChoice()),
      reset: () => {
        setNumericChoice(DEFAULT_NUMERIC_ID);
        refresh();
      },
    },
    fontSize: {
      value: getFontSizeChoice(),
      def: FONT_SIZE_DEFAULT,
      display: `${getFontSizeChoice()}%`,
      reset: () => {
        setFontSizeChoice(FONT_SIZE_DEFAULT);
        refresh();
      },
    },
    lang: {
      value: currentLang,
      def: systemLang(),
      // 语言名用 LANGS 里的自有标签（"中文" / "English"）——不新增 key，也不跟着界面语言翻
      display: LANGS.find((item) => item.value === currentLang)?.label ?? currentLang,
      reset: () => {
        void i18n.changeLanguage(systemLang());
        refresh();
      },
    },
    // 桌面端才有这两条通道：浏览器直连时给 null，那一项就不出现在列表里
    zoom:
      hasDesktopPrefs() && prefs
        ? {
            value: prefs.level,
            def: 0,
            display: `${prefs.percent}%`,
            reset: () => {
              // 通道可能已经不在（窗口销毁 / 浏览器态）：拿不到 Promise 也要刷新，
              // 否则列表会一直显示旧值——"点了还原但显示没变"比不刷新更难解释
              void (setZoomLevel(0, true) ?? Promise.resolve()).then(refresh);
            },
          }
        : null,
    // 笔 5：到点提醒（默认开；真值在主进程，它才是发通知的那一方）
    reminders:
      hasDesktopPrefs() && prefs
        ? {
            value: prefs.reminders,
            def: true,
            display: prefs.reminders ? i18n.t("settings.toggleOn") : i18n.t("settings.toggleOff"),
            reset: () => {
              void (setReminders(true) ?? Promise.resolve()).then(refresh);
            },
            set: (next: boolean) => {
              void (setReminders(next) ?? Promise.resolve()).then(refresh);
            },
          }
        : null,
    // 「提前几天开始提醒」（3/5/7）：与开关同一通道（真值都在主进程）
    reminderDays:
      hasDesktopPrefs() && prefs
        ? {
            value: String(prefs.reminderDays ?? 3),
            def: "3",
            display: i18n.t("settings.reminderDaysValue", { days: prefs.reminderDays ?? 3 }),
            reset: () => {
              void (setReminders({ days: 3 }) ?? Promise.resolve()).then(refresh);
            },
            options: ["3", "5", "7"],
            set: (next: string) => {
              void (setReminders({ days: Number(next) }) ?? Promise.resolve()).then(refresh);
            },
          }
        : null,
  };

  return { entries: buildPreferenceEntries(sources), refresh, version };
}
