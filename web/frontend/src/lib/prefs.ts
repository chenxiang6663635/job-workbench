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
}

interface JobwsPrefs {
  get(): Promise<PrefsSnapshot>;
  setZoomLevel(level: number, persist?: boolean): Promise<{ level: number; percent: number }>;
  setLang(lang: string): Promise<{ lang: string }>;
  onZoomChanged(cb: (payload: { level: number; percent: number }) => void): () => void;
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
