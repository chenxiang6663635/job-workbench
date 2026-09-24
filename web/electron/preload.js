// 渲染进程 ↔ 主进程的偏好通道（contextBridge）。
//
// 为什么需要它：窗口开在 contextIsolation 下，渲染进程拿不到 Node / Electron API；
// 而「界面大小」与「界面语言」这两项偏好的**真值在主进程**——缩放级别还要驱动
// 原生层（webContents.setZoomLevel）与更新对话框的文案，语言同理。所以前端只能
// 「表达意图」，由主进程统一夹取、落盘并广播（单一真值，避免滑块与 Ctrl± 各算一套）。
//
// 暴露面刻意保持最小：一个命名空间、四个方法，全是纯数据进出，不做任意通道转发
// （转发任意 channel 等于把 ipcRenderer 整个交出去，contextIsolation 就白设了）。
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jobwsPrefs", {
  /** 读当前偏好：{ level, min, max, step, percent, lang } */
  get: () => ipcRenderer.invoke("prefs:get"),

  /** 设置缩放级别。`persist=false` 用于拖动中的实时预览（只改内存与画面，不落盘、
      不广播）；松手时以 `persist=true` 再调一次落盘。主进程负责夹取与 setZoomLevel。 */
  setZoomLevel: (level, persist = true) => ipcRenderer.invoke("prefs:set-zoom", { level, persist }),

  /** 上报界面语言：主进程据此渲染窗口标题与更新对话框（见 i18n.js 顶部的取舍说明） */
  setLang: (lang) => ipcRenderer.invoke("prefs:set-lang", lang),

  /** 上报当前工作区：主进程的到点提醒要按**用户实际在用的工作区**查（否则多工作区用户
      收到的是默认工作区的提醒）。真值仍在渲染进程（localStorage），这里只做转达。 */
  setWorkspace: (ws) => ipcRenderer.invoke("prefs:set-workspace", ws),

  /** 到点提醒：开关 + 提前天数（真值在主进程：它才是发通知的那一方）。
      旧调用点只传布尔，设置页传 `{ enabled?, days? }`——主进程两端都收。 */
  setReminders: (value) => ipcRenderer.invoke("prefs:set-reminders", value),

  /** 订阅缩放变化（来自快捷键或其它窗口），返回取消订阅函数 */
  onZoomChanged: (cb) => {
    const listener = (_event, payload) => cb(payload);
    ipcRenderer.on("prefs:zoom-changed", listener);
    return () => ipcRenderer.removeListener("prefs:zoom-changed", listener);
  },

  /** 订阅"通知被点击"：主进程送来要定位的记录 id，界面据此跳到追踪表并展开该行 */
  onReminderFocus: (cb) => {
    const listener = (_event, payload) => cb(payload);
    ipcRenderer.on("reminder:focus", listener);
    return () => ipcRenderer.removeListener("reminder:focus", listener);
  },
});
