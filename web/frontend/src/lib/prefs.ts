// 桌面端偏好通道的渲染侧封装（对应 web/electron/preload.js 暴露的 window.jobwsPrefs）。
//
// 什么时候不存在：直接用浏览器打开 8765（开发态 / Web 形态）时没有 preload，
// window.jobwsPrefs 为 undefined——界面据此降级为一句只读说明，而不是报错。
// 用「可选」而不是「必选 + 抛错」的原因：这个模块在两种宿主里都要能跑
// （UI 冒烟就是跑在浏览器里的），把宿主差异收在这一层，调用方只关心返回值。

export interface PrefsSnapshot {
  level: number;
  min: number;
  max: number;
  step: number;
  percent: number;
  lang: string;
  /** 到点提醒开关（笔 5）：真值在主进程——它才是发通知的那一方 */
  reminders: boolean;
  /** 「提前几天开始提醒」（3/5/7，默认 3）：与开关一样，真值在主进程 */
  reminderDays: number;
  /** 渲染进程上报过的工作区（空串 = 未上报，后端按默认工作区查） */
  workspace: string;
}

/** 到点提醒的改动：旧调用点只传布尔，设置页传 `{ enabled?, days? }` */
export type ReminderPatch = boolean | { enabled?: boolean; days?: number };

interface JobwsPrefs {
  get(): Promise<PrefsSnapshot>;
  setZoomLevel(level: number, persist?: boolean): Promise<{ level: number; percent: number }>;
  setLang(lang: string): Promise<{ lang: string }>;
  setWorkspace(ws: string): Promise<{ workspace: string }>;
  setReminders(value: ReminderPatch): Promise<{ reminders: boolean; reminderDays: number }>;
  onZoomChanged(cb: (payload: { level: number; percent: number }) => void): () => void;
  onReminderFocus(cb: (payload: { id?: string }) => void): () => void;
  /** 打开日志文件夹（2026-09-25 支持性批）。**可选**：更早版本的桌面壳没有这个方法 */
  openLogFolder?(): Promise<string>;
}

declare global {
  interface Window {
    jobwsPrefs?: JobwsPrefs;
  }
}

/** 是否运行在桌面壳里（存在偏好通道）。 */
export function hasDesktopPrefs(): boolean {
  return typeof window !== "undefined" && !!window.jobwsPrefs;
}

/** 读当前偏好；无通道时返回 null（调用方据此显示降级说明）。 */
export function getPrefs(): Promise<PrefsSnapshot> | null {
  return window.jobwsPrefs ? window.jobwsPrefs.get() : null;
}

/** 设置缩放级别：persist=false 只预览不落盘（拖动中），松手时传 true。 */
export function setZoomLevel(level: number, persist = true) {
  return window.jobwsPrefs?.setZoomLevel(level, persist);
}

/** 上报界面语言：主进程据此渲染窗口标题与更新对话框（见 web/electron/i18n.js 顶部）。 */
export function reportLang(lang: string) {
  return window.jobwsPrefs?.setLang(lang);
}

/**
 * 通道句柄：无 `window` 的环境（vitest 单测——本仓刻意不装 jsdom）与浏览器形态都返回 undefined。
 *
 * 为什么这一条要显式判 `typeof window`：`setWorkspace` 是 lib/http 里**每个请求都会走**的
 * 函数，它现在顺带上报工作区；少了这层判断，单测里第一次 setWorkspace 就 ReferenceError
 * （http.test.ts 13 条全红就是这么来的）。
 */
function prefsBridge() {
  return typeof window === "undefined" ? undefined : window.jobwsPrefs;
}

/** 上报当前工作区：主进程的到点提醒按它查询（多工作区用户才不会收到默认工作区的提醒）。 */
export function reportWorkspace(ws: string) {
  return prefsBridge()?.setWorkspace(ws);
}

/** 到点提醒（开关 / 提前天数）：真值在主进程（它发通知），这里只表达意图。 */
export function setReminders(value: ReminderPatch) {
  return prefsBridge()?.setReminders(value);
}

/**
 * 订阅"通知被点击"：主进程把要定位的记录 id 送过来（无 id 时不回调）。
 *
 * 没有这一层的话，点通知只能把窗口拉到前面——用户还要自己在追踪表里找那一条，
 * 而通知的全部意义就是"让你立刻看到它"。
 */
export function onReminderFocus(cb: (id: string) => void): () => void {
  const bridge = prefsBridge();
  if (!bridge?.onReminderFocus) return () => {};
  return bridge.onReminderFocus((payload) => {
    const id = payload && typeof payload.id === "string" ? payload.id : "";
    if (id) cb(id);
  });
}

/** 桌面壳是否支持「打开日志文件夹」（更早的壳没有该方法，Web 形态没有通道）。 */
export function canOpenLogFolder(): boolean {
  return !!prefsBridge()?.openLogFolder;
}

/** 打开日志文件夹（设置页「关于」卡）：日志与数据同在 userData（%APPDATA%\job-workbench）。 */
export function openLogFolder() {
  return prefsBridge()?.openLogFolder?.();
}

/** 订阅缩放变化（来自快捷键或其它窗口）；无通道时是空订阅。
    回调前做一次形状兜底：主进程日后换结构时，宁可不更新，也不要写进 NaN。 */
export function onZoomChanged(
  cb: (payload: { level: number; percent: number }) => void,
): () => void {
  if (!window.jobwsPrefs) return () => {};
  return window.jobwsPrefs.onZoomChanged((payload) => {
    if (!payload || !Number.isFinite(payload.level) || !Number.isFinite(payload.percent)) return;
    cb(payload);
  });
}
