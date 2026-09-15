// 主题注册表与应用层（批 4）
//
// 设计（对齐 shadcn 官方模式与本仓库既有变量结构）：
// - 每套主题 = 一组 `[data-theme="<id>"]` CSS 变量（src/themes/*.css，独立文件，文件头注明上游与许可）
// - **默认暗主题不写属性**（:root 即它），因此「切回 Dark」= 移除 data-theme
// - 「跟随系统」是 JS 层的解析：监听 prefers-color-scheme，在 dark / light 之间动态切换
// - 持久化用 localStorage（设备级偏好，与界面语言、缩放同类）；跨端的工作区偏好见批 4 的 4f
// - 切换只改根属性，不触发组件重渲染（变量由 CSS 承接，零运行时开销）

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

/** 已知主题 id 集合（含 system 与 dark）——校验用户选择，拒绝未知值。 */
const KNOWN_IDS = new Set(THEMES.map((item) => item.id));

/** 读用户选择；无存储/存储被清/未知值 → 跟随系统。 */
export function getThemeChoice(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && KNOWN_IDS.has(stored) ? stored : SYSTEM_ID;
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
  const safe = KNOWN_IDS.has(id) ? id : SYSTEM_ID;
  try {
    localStorage.setItem(STORAGE_KEY, safe);
  } catch {
    // 持久化失败只影响下次启动的默认值，不影响本次会话
  }
  applyTheme(safe);
}

/** 启动时调用（main.tsx）：应用已存选择。 */
export function applyStoredTheme(): void {
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
