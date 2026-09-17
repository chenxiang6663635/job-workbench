// 字体方案与界面字号（批 4 的 4g / #4；2026-09-17 实测反馈批从 theme.ts 拆出）
//
// 为什么单独一个文件：主题（theme.ts）管颜色变量的注册与应用，字体/字号是
// 另一条排版线——三处引用同一份口径（设置页 ThemePicker、首帧防闪脚本
// index.html、启动同步 main.tsx）。拆开后 theme.ts 回到"只管主题"。
//
// 三个选择（主题/字体/字号）都是**设备级偏好**（localStorage，随这台机器），
// 与工作区级偏好（tools/prefs.py 的 config/preferences.json）是两个分层，
// 互不覆盖（prefs.py 文件头有同款说明）。

// --- 界面字体 ---------------------------------------------------------------

const FONT_KEY = "jobws.font";

export interface FontOption {
  id: string;
  label: string;
}

// default = Inter Variable（本地打包，拉丁 UI 与数字最佳）；
// system = 纯系统栈（不加载 webfont，启动更快、离线更轻）；serif = Times + 宋体。
// 实现只写 html[data-font]——栈本体在 index.css 的 --font-sans-stack 变量里。
// （2026-09-17 收尾批会扩到 10+ 款，见后续笔。）
export const FONTS: FontOption[] = [
  { id: "default", label: "Inter" },
  { id: "system", label: "System UI" },
  { id: "serif", label: "serif" },
];

const FONT_IDS = ["default", "system", "serif"] as const;

export function getFontChoice(): string {
  try {
    const stored = localStorage.getItem(FONT_KEY) || "default";
    return (FONT_IDS as readonly string[]).includes(stored) ? stored : "default";
  } catch {
    return "default";
  }
}

export function applyFont(choice: string): void {
  const root = document.documentElement;
  if (choice === "system" || choice === "serif") {
    root.setAttribute("data-font", choice);
  } else {
    root.removeAttribute("data-font");
  }
}

export function setFontChoice(id: string): void {
  const safe = (FONT_IDS as readonly string[]).includes(id) ? id : "default";
  try {
    localStorage.setItem(FONT_KEY, safe);
  } catch {
    // 同主题：持久化失败只影响下次启动
  }
  applyFont(safe);
}

export function applyStoredFont(): void {
  applyFont(getFontChoice());
}

// --- 界面字号（#4；2026-09-17 实测反馈改连续）--------------------------------
//
// 只改**根字号百分比**（Tailwind 的长度单位全是 rem，全站等比跟随）；与
// Electron 的 webContents 全局缩放解耦——浏览器端同样可用，且百分比写法
// 尊重用户系统的默认字号。与界面缩放可以叠加（缩放放大像素，字号放大文字）。
//
// 2026-09-17 起从四档（87.5/100/112.5/125）改为**连续 80–150%（步进 5）**：
// 档位制覆盖不了介于两档之间的实际需求（实测反馈「为什么不能和界面放缩一样
// 灵活挑」）。历史档位值读取时映射迁移，旧偏好不丢。

const FONTSIZE_KEY = "jobws.fontsize";

export const FONT_SIZE_MIN = 80;
export const FONT_SIZE_MAX = 150;
export const FONT_SIZE_STEP = 5;
export const FONT_SIZE_DEFAULT = 100;

/** 历史四档 → 百分比（2026-09-17 之前的存储格式，读取时迁移）。 */
const LEGACY_FONT_SIZES: Record<string, number> = {
  sm: 87.5,
  base: 100,
  lg: 112.5,
  xl: 125,
};

/** 吸附到步进网格、夹取到 [MIN, MAX]；非法值（NaN / ±Infinity）回落默认值。 */
export function clampFontSize(pct: number): number {
  if (!Number.isFinite(pct)) return FONT_SIZE_DEFAULT;
  const snapped = Math.round(pct / FONT_SIZE_STEP) * FONT_SIZE_STEP;
  return Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, snapped));
}

export function getFontSizeChoice(): number {
  try {
    const stored = localStorage.getItem(FONTSIZE_KEY);
    if (!stored) return FONT_SIZE_DEFAULT;
    if (Object.prototype.hasOwnProperty.call(LEGACY_FONT_SIZES, stored)) {
      return LEGACY_FONT_SIZES[stored];
    }
    return clampFontSize(parseFloat(stored));
  } catch {
    return FONT_SIZE_DEFAULT;
  }
}

export function applyFontSize(pct: number): void {
  const root = document.documentElement;
  if (pct === FONT_SIZE_DEFAULT) {
    // 100% 清掉内联值（与"未设置"等价）：根元素保持干净，排查样式时少一层噪声
    root.style.removeProperty("font-size");
  } else {
    root.style.fontSize = pct + "%";
  }
}

export function setFontSizeChoice(pct: number): void {
  const safe = clampFontSize(pct);
  try {
    localStorage.setItem(FONTSIZE_KEY, String(safe));
  } catch {
    // 同主题：持久化失败只影响下次启动
  }
  applyFontSize(safe);
}

export function applyStoredFontSize(): void {
  applyFontSize(getFontSizeChoice());
}
