// 主题注册表与应用层（批 4）
//
// 设计（对齐 shadcn 官方模式与本仓库既有变量结构）：
// - 每套主题 = 一组 `[data-theme="<id>"]` CSS 变量（src/themes/*.css，独立文件，文件头注明上游与许可）
// - **默认暗主题不写属性**（:root 即它），因此「切回 Dark」= 移除 data-theme
// - 「跟随系统」是 JS 层的解析：监听 prefers-color-scheme，在 dark / light 之间动态切换
// - 持久化用 localStorage（设备级偏好，与界面语言、缩放同类）；跨端的工作区偏好见批 4 的 4f
// - 切换只改根属性，不触发组件重渲染（变量由 CSS 承接，零运行时开销）

import { hslToRgb, parseHslTriple } from "./contrast";

const STORAGE_KEY = "jobws.theme";
/** 「跟随系统」选项 id（非真实主题，由 JS 解析到 dark / light）。 */
export const SYSTEM_ID = "system";
/** 默认暗主题 id：应用时移除 data-theme 属性（:root 即它）。 */
export const DEFAULT_ID = "dark";

export interface ThemeOption {
  id: string;
  /** 主题真名（社区惯例不翻译）；system 项的显示名走 i18n（settings.themeSystem） */
  label: string;
  /** 预览色块：[背景, 卡片, 主色]，取各自官方色板 */
  swatch: [string, string, string];
}

/** 首批内置主题（与 src/themes/*.css 一一对应；dark 无独立文件）。 */
export const THEMES: ThemeOption[] = [
  { id: SYSTEM_ID, label: "System", swatch: ["#0b1220", "#1c2333", "#38bdf8"] },
  { id: "dark", label: "Dark", swatch: ["#0b1220", "#1c2333", "#38bdf8"] },
  { id: "light", label: "Light", swatch: ["#f7f8fa", "#ffffff", "#0284c7"] },
  { id: "catppuccin-mocha", label: "Catppuccin Mocha", swatch: ["#1e1e2e", "#313244", "#89b4fa"] },
  { id: "catppuccin-latte", label: "Catppuccin Latte", swatch: ["#e6e9ef", "#eff1f5", "#1e66f5"] },
  { id: "nord", label: "Nord", swatch: ["#2e3440", "#3b4252", "#88c0d0"] },
  { id: "tokyo-night", label: "Tokyo Night", swatch: ["#1a1b26", "#24283b", "#7aa2f7"] },
  { id: "rose-pine", label: "Rosé Pine", swatch: ["#191724", "#1f1d2e", "#c4a7e7"] },
  { id: "rose-pine-dawn", label: "Rosé Pine Dawn", swatch: ["#faf4ed", "#fffaf3", "#286983"] },
  { id: "gruvbox", label: "Gruvbox", swatch: ["#282828", "#3c3836", "#fabd2f"] },
  { id: "everforest", label: "Everforest", swatch: ["#2d353b", "#343f44", "#a7c080"] },
];

/** 内置主题 id 集合（含 system 与 dark）。 */
const BUILTIN_IDS = new Set(THEMES.map((item) => item.id));

/** 主题变量全集（45 键）——与 tools/check_themes.py 的基准清单、主题文件同构。
    编辑器「从当前主题继承全部、只改关键色」靠它列举与校验。 */
export const THEME_VAR_KEYS = [
  "background", "foreground", "card", "card-foreground", "popover",
  "popover-foreground", "primary", "primary-foreground", "secondary",
  "secondary-foreground", "muted", "muted-foreground", "destructive",
  "destructive-foreground", "success", "warning", "border", "border-strong",
  "input", "ring", "highlight", "scrim", "glow-primary",
  "elevation-0-surface", "elevation-1-surface", "elevation-2-surface",
  "elevation-3-surface",
  "elevation-1-border", "elevation-2-border", "elevation-3-border",
  "elevation-1-shadow", "elevation-2-shadow", "elevation-3-shadow",
  "shadow-card", "shadow-elevated", "card-gradient", "hero-glow",
  "chart-1", "chart-2", "chart-3", "chart-4", "chart-5", "chart-6",
  "chart-7", "chart-8",
];

/** 全部已知主题 id（内置 + 自定义）——校验用户选择、拒绝未知值。 */
function knownIds(): Set<string> {
  const ids = new Set(BUILTIN_IDS);
  for (const theme of getCustomThemes()) ids.add(theme.id);
  return ids;
}

/** 读用户选择；无存储/存储被清/未知值 → 跟随系统。 */
export function getThemeChoice(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && knownIds().has(stored) ? stored : SYSTEM_ID;
  } catch {
    return SYSTEM_ID;
  }
}

function resolveSystem(): string {
  try {
    return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : DEFAULT_ID;
  } catch {
    return DEFAULT_ID;
  }
}

/** 把选择解析成真实主题 id（system → dark/light）。 */
export function resolveTheme(choice: string): string {
  return choice === SYSTEM_ID ? resolveSystem() : choice;
}

/** 应用主题：默认暗移除属性；其余写 data-theme（CSS 变量由 themes/*.css 承接）。 */
export function applyTheme(choice: string): void {
  const root = document.documentElement;
  const resolved = resolveTheme(choice);
  if (resolved === DEFAULT_ID) {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", resolved);
  }
  root.setAttribute("data-theme-choice", choice);
  ensureSystemListener(choice);
}

/** 设置并持久化（未知 id 静默回落到默认，不写脏数据）。 */
export function setThemeChoice(id: string): void {
  const safe = knownIds().has(id) ? id : SYSTEM_ID;
  try {
    localStorage.setItem(STORAGE_KEY, safe);
  } catch {
    // 持久化失败只影响下次启动的默认值，不影响本次会话
  }
  applyTheme(safe);
}

/** 启动时调用（main.tsx）：应用已存选择（含自定义主题的 CSS 注入）。 */
export function applyStoredTheme(): void {
  // 自定义主题的 CSS 存 localStorage、运行时注入 <style>——刷新后若不先注入，
  // data-theme="custom-*" 命中不了任何规则块、会静默回落成默认暗，而设置页
  // 仍勾着该自定义主题（独立审查 MAJOR）。
  injectCustomCss();
  applyTheme(getThemeChoice());
}

// 仅在「跟随系统」时监听系统主题变化；重复 apply 不会叠加监听。
let mediaListener: ((event: MediaQueryListEvent) => void) | null = null;
function ensureSystemListener(choice: string): void {
  try {
    const mq = window.matchMedia("(prefers-color-scheme: light)");
    if (choice !== SYSTEM_ID) {
      if (mediaListener) {
        mq.removeEventListener("change", mediaListener);
        mediaListener = null;
      }
      return;
    }
    if (mediaListener) return;
    mediaListener = () => applyTheme(SYSTEM_ID);
    mq.addEventListener("change", mediaListener);
  } catch {
    // matchMedia 不可用（极老宿主）时退化为默认暗，不影响功能
  }
}

// --- 自定义主题（批 4 编辑器）-----------------------------------------------
//
// 自定义主题 = 一份变量表（45 键，HSL 三元组），存 localStorage 的 JSON 数组，
// 以动态 <style> 注入 CSS（避免每次编辑都写文件/重构建）。与内置主题共用同一
// 应用路径：applyTheme 认 id、CSS 认 [data-theme]——编辑器只是「造变量表」的那一层。

const CUSTOM_KEY = "jobws.theme.custom";
const CUSTOM_STYLE_ID = "jobws-custom-themes";

export interface CustomTheme {
  id: string;
  /** 用户命名（显示在主题网格里） */
  label: string;
  /** 45 键变量表（与内置主题文件同构） */
  vars: Record<string, string>;
}

/** 读全部自定义主题（坏 JSON 静默视为空——不阻塞启动）。 */
export function getCustomThemes(): CustomTheme[] {
  try {
    const raw = localStorage.getItem(CUSTOM_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is CustomTheme =>
        !!item && typeof item.id === "string" && typeof item.label === "string" &&
        !!item.vars && typeof item.vars === "object"
    );
  } catch {
    return [];
  }
}

function persistCustomThemes(themes: CustomTheme[]): void {
  try {
    localStorage.setItem(CUSTOM_KEY, JSON.stringify(themes));
  } catch {
    // 持久化失败只影响下次启动；本次会话仍可预览
  }
  injectCustomCss(themes);
}

/** 生成并注入自定义主题的 CSS（每次增删改重写整块，幂等）。 */
export function injectCustomCss(themes = getCustomThemes()): void {
  if (typeof document === "undefined") return;
  let style = document.getElementById(CUSTOM_STYLE_ID) as HTMLStyleElement | null;
  if (!themes.length) {
    if (style) style.remove();
    return;
  }
  if (!style) {
    style = document.createElement("style");
    style.id = CUSTOM_STYLE_ID;
    document.head.appendChild(style);
  }
  style.textContent = themes
    .map((theme) => {
      const body = Object.keys(theme.vars)
        .map((key) => `  --${key}: ${theme.vars[key]};`)
        .join("\n");
      return `[data-theme="${theme.id}"] {\n${body}\n}`;
    })
    .join("\n\n");
}

/** 新增或覆盖一个自定义主题，并立刻应用它。 */
export function saveCustomTheme(theme: CustomTheme): void {
  const themes = getCustomThemes().filter((item) => item.id !== theme.id);
  themes.push(theme);
  persistCustomThemes(themes);
  setThemeChoice(theme.id);
}

export function removeCustomTheme(id: string): void {
  const themes = getCustomThemes().filter((item) => item.id !== id);
  persistCustomThemes(themes);
  if (getThemeChoice() === id) setThemeChoice(SYSTEM_ID);
}

/** 内置 + 自定义的完整清单（外观卡与编辑器都读它）。 */
export function listThemes(): ThemeOption[] {
  const builtinPrefix = THEMES.slice(0, 2); // system + dark
  const builtinRest = THEMES.slice(2);
  const custom: ThemeOption[] = getCustomThemes().map((theme) => ({
    id: theme.id,
    label: theme.label,
    swatch: [
      toHexOr(theme.vars["background"], "#0b1220"),
      toHexOr(theme.vars["card"], "#1c2333"),
      toHexOr(theme.vars["primary"], "#38bdf8"),
    ] as [string, string, string],
  }));
  return [...builtinPrefix, ...custom, ...builtinRest];
}

function toHexOr(triple: string | undefined, fallback: string): string {
  const parsed = parseHslTriple(triple || "");
  if (!parsed) return fallback;
  const rgb = hslToRgb(parsed);
  const to = (c: number) => Math.round(c * 255).toString(16).padStart(2, "0");
  return `#${to(rgb[0])}${to(rgb[1])}${to(rgb[2])}`;
}

/** 导出一个主题（内置取文档里的变量，自定义取存储）为可分享的 JSON 文本。 */
export function exportThemeVars(vars: Record<string, string>): string {
  return JSON.stringify({ version: 1, vars }, null, 2);
}

/** 解析导入文本：支持本仓库 JSON 与 tweakcn / shadcn 的 `--key: value;` CSS。 */
export function parseThemeImport(text: string): Record<string, string> | null {
  const trimmed = (text || "").trim();
  if (!trimmed) return null;
  if (trimmed.startsWith("{")) {
    try {
      const parsed = JSON.parse(trimmed);
      const vars = parsed && (parsed.vars || parsed);
      if (vars && typeof vars === "object") return normalizeVars(vars);
    } catch {
      return null;
    }
    return null;
  }
  const vars: Record<string, string> = {};
  const re = /--([a-zA-Z0-9-]+)\s*:\s*([^;]+);/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(trimmed))) {
    vars[match[1]] = normalizeValue(match[2].trim());
  }
  return Object.keys(vars).length ? normalizeVars(vars) : null;
}

/** tweakcn/shadcn 导出常见 `0 0% 100%`（本仓库格式）与 `hsl(0 0% 100%)` 两种写法。 */
function normalizeValue(value: string): string {
  const inner = /^hsla?\(([^)]+)\)$/i.exec(value);
  return (inner ? inner[1] : value).trim();
}

/** 只保留 45 键里认识的键，值归一化为三元组。 */
function normalizeVars(vars: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of Object.keys(vars)) {
    const value = normalizeValue(String(vars[key]));
    if (/^\s*[\d.]+\s+[\d.]+%\s+[\d.]+%\s*$/.test(value)) out[key] = value;
  }
  return out;
}

// --- 字体方案与界面字号已迁至 ./fonts（2026-09-17 实测反馈批）-----------------
//
// 主题（本文件）只管颜色变量的注册与应用；字体/字号是另一条排版线，且有三处
// 引用同一份口径（设置页 ThemePicker、首帧防闪脚本 index.html、启动同步
// main.tsx），故拆为 lib/fonts.ts。这里 re-export 保持既有导入路径零改动。

export {
  FONTS,
  FONT_SIZE_DEFAULT,
  FONT_SIZE_MAX,
  FONT_SIZE_MIN,
  FONT_SIZE_STEP,
  applyFont,
  applyFontSize,
  applyStoredFont,
  applyStoredFontSize,
  clampFontSize,
  getFontChoice,
  getFontSizeChoice,
  setFontChoice,
  setFontSizeChoice,
} from "./fonts";
export type { FontOption } from "./fonts";
