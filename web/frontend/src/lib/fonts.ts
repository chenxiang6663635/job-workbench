// 字体方案与界面字号（批 4 的 4g / #4；2026-09-17 实测反馈批从 theme.ts 拆出）
//
// 为什么单独一个文件：主题（theme.ts）管颜色变量的注册与应用，字体/字号是
// 另一条排版线——三处引用同一份口径（设置页 ThemePicker、首帧防闪脚本
// index.html、启动同步 main.tsx）。拆开后 theme.ts 回到"只管主题"。
//
// 几个选择（主题/字体/等宽/数字/字号）都是**设备级偏好**（localStorage，随这台
// 机器），与工作区级偏好（tools/prefs.py 的 config/preferences.json）是两个
// 分层，互不覆盖（prefs.py 文件头有同款说明）。

// --- 界面字体 ---------------------------------------------------------------

const FONT_KEY = "jobws.font";

export interface FontOption {
  id: string;
  label: string;
}

// 全部**本地打包**（Fontsource，OFL-1.1，离线可用）；各款只含拉丁——中文始终
// 回退系统栈（见 index.css 的 --font-cjk）。栈本体在 index.css：每个 id 对应
// 一条 `html[data-font="<id>"] { --font-latin: … }`——**id 两边必须同步**
// （CSS 不被门禁扫描，靠这段注释与设置页列表人工兜住）。
// system 不加载 webfont（启动更快、离线更轻）；serif = Times + 系统宋体。
export const FONTS: FontOption[] = [
  { id: "inter", label: "Inter" },
  { id: "geist", label: "Geist" },
  { id: "plex", label: "IBM Plex Sans" },
  { id: "manrope", label: "Manrope" },
  { id: "jakarta", label: "Plus Jakarta Sans" },
  { id: "dm", label: "DM Sans" },
  { id: "figtree", label: "Figtree" },
  { id: "outfit", label: "Outfit" },
  { id: "public", label: "Public Sans" },
  { id: "source3", label: "Source Sans 3" },
  { id: "work", label: "Work Sans" },
  { id: "atkinson", label: "Atkinson Hyperlegible" },
  { id: "system", label: "System UI" },
  { id: "serif", label: "serif" },
];

const FONT_IDS = new Set(FONTS.map((f) => f.id));

/** 历史值迁移：2026-09-17 之前 default = Inter（且不写属性，:root 即它）。 */
const LEGACY_FONT_IDS: Record<string, string> = { default: "inter" };

function normalizeFontId(id: string): string {
  const migrated = LEGACY_FONT_IDS[id] ?? id;
  return FONT_IDS.has(migrated) ? migrated : "inter";
}

export function getFontChoice(): string {
  try {
    return normalizeFontId(localStorage.getItem(FONT_KEY) || "inter");
  } catch {
    return "inter";
  }
}

/** 写 html[data-font]：栈本体由 index.css 按 id 承接（inter 命中 :root 默认）。 */
export function applyFont(choice: string): void {
  document.documentElement.setAttribute("data-font", normalizeFontId(choice));
}

export function setFontChoice(id: string): void {
  const safe = normalizeFontId(id);
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

// --- 等宽字体（第二槽；2026-09-17 收尾批，批 4.6 起只服务"非数值"场景）------
//
// 独立于界面字体的第二槽：作用于 --font-mono-stack——代码片段、编号（记录 id /
// 邮件 id）与日期时间。**数值不走它**：数值归第三槽 --font-numeric（见下方
// 「数字字体」段），正文内联数字走界面字体的 tabular-nums。

const MONO_KEY = "jobws.mono";

export const MONOS: FontOption[] = [
  { id: "maple", label: "Maple Mono" },
  { id: "jetbrains", label: "JetBrains Mono" },
  { id: "fira", label: "Fira Code" },
  { id: "geist-mono", label: "Geist Mono" },
  { id: "plex-mono", label: "IBM Plex Mono" },
  { id: "source-code", label: "Source Code Pro" },
];

const MONO_IDS = new Set(MONOS.map((m) => m.id));

function normalizeMonoId(id: string): string {
  return MONO_IDS.has(id) ? id : "maple";
}

export function getMonoChoice(): string {
  try {
    return normalizeMonoId(localStorage.getItem(MONO_KEY) || "maple");
  } catch {
    return "maple";
  }
}

export function applyMono(choice: string): void {
  document.documentElement.setAttribute("data-mono", normalizeMonoId(choice));
}

export function setMonoChoice(id: string): void {
  const safe = normalizeMonoId(id);
  try {
    localStorage.setItem(MONO_KEY, safe);
  } catch {
    // 同主题：持久化失败只影响下次启动
  }
  applyMono(safe);
}

export function applyStoredMono(): void {
  applyMono(getMonoChoice());
}

// --- 数字字体（第三槽；批 4.6）-----------------------------------------------
//
// 独立于界面字体与等宽槽的第三槽：作用于 --font-numeric-stack——**数值**
// （KPI 主数字、计数、天数、百分比、评分）。等宽槽继续管代码 / 编号 / 日期
// 时间；正文内联数字仍走界面字体的 tabular-nums（<Num numeric={false}>
// 可显式退出数字槽）。
//
// 为什么不复用等宽槽：数字的"接缝感"来自跨气质配对（2026-09-17 调研与对比图
// 实测）——数字槽候选因此收敛为能与主流界面字体同超家族配对的款，等宽槽则
// 保持全量候选。id 三处必须同步：index.css 的 --font-numeric 规则、本列表、
// 设置页下拉（同 FONTS / MONOS 的人工兜底约定）。
//
// "follow" = 跟随界面字体（关闭数字槽，回到界面字体 tabular 的行为）；
// 默认款 = 用户从三款对比图选定（2026-09-17）。

const NUMERIC_KEY = "jobws.numeric";

/** 数字槽默认款：2026-09-17 三款同条件对比图实测选定（详见批 4.6 计划）。 */
export const DEFAULT_NUMERIC_ID = "geist-mono";

export const NUMERICS: FontOption[] = [
  { id: DEFAULT_NUMERIC_ID, label: "Geist Mono" },
  { id: "jetbrains", label: "JetBrains Mono" },
  { id: "plex-mono", label: "IBM Plex Mono" },
  // 展示名由设置页按语言给（settings.fontFollow）；字体真名不翻译
  { id: "follow", label: "Follow" },
];

const NUMERIC_IDS = new Set(NUMERICS.map((n) => n.id));

/** 归一化（导出供单测）：未登记 id 与空串回落默认款。 */
export function normalizeNumericId(id: string): string {
  return NUMERIC_IDS.has(id) ? id : DEFAULT_NUMERIC_ID;
}

export function getNumericChoice(): string {
  try {
    return normalizeNumericId(localStorage.getItem(NUMERIC_KEY) || DEFAULT_NUMERIC_ID);
  } catch {
    return DEFAULT_NUMERIC_ID;
  }
}

/** 写 html[data-numeric]：栈本体由 index.css 按 id 承接（默认款命中 :root）。 */
export function applyNumeric(choice: string): void {
  document.documentElement.setAttribute("data-numeric", normalizeNumericId(choice));
}

export function setNumericChoice(id: string): void {
  const safe = normalizeNumericId(id);
  try {
    localStorage.setItem(NUMERIC_KEY, safe);
  } catch {
    // 同主题：持久化失败只影响下次启动
  }
  applyNumeric(safe);
}

export function applyStoredNumeric(): void {
  applyNumeric(getNumericChoice());
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
      // 过一遍 clamp：87.5 不在 80–150 的 5% 步进网格上，滑块会自行吸附导致
      // 显示值与 thumb 不一致（独立审查 NIT）——读取时就吸附一致。
      return clampFontSize(LEGACY_FONT_SIZES[stored]);
    }
    return clampFontSize(parseFloat(stored));
  } catch {
    return FONT_SIZE_DEFAULT;
  }
}

export function applyFontSize(pct: number): void {
  const root = document.documentElement;
  // 同时写一个 data 属性：设置页的「外观与偏好」状态卡靠**根属性变化**感知偏好被改过
  // （hooks/usePreferenceEntries.ts 的 MutationObserver）。只写 style 的话，观察器要么
  // 漏掉字号、要么得盯整个 style 属性（主题编辑器每敲一个色值都会触发一轮刷新）。
  root.setAttribute("data-fontsize", String(clampFontSize(pct)));
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
