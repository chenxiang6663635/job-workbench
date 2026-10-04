// 求职工作台 · Electron 主进程（composition root）
// 职责：探测 Python → 拉起后端 → 等 /api/health 就绪 → 开窗口加载界面
//       → 关闭窗口时结束后端进程。
// 前端静态产物由 FastAPI 同源托管（web/frontend/dist），无需 vite dev server，
// 也无需放宽 CORS —— 页面与 API 同源。
//
// 2026-10-04（#204）：967 行收敛为装配根，功能段原样搬进同目录模块（行为零变更）：
//   logger.js              日志落盘与 1MB 轮转
//   backend_process.js     Python 探测 / 健康检查 / 启停后端
//   prefs.js               缩放与界面语言偏好（prefs:set-zoom / prefs:set-lang）
//   diagnostics_bridge.js  用户提示 / 复制诊断信息 / 打开日志目录
//   notifications.js       到点提醒（prefs:set-workspace / prefs:set-reminders）
//   window.js              窗口状态记忆与建窗
//   navigation.js          导航守卫接线与 CSP
//   updater.js             自动更新
//   single_instance.js     AUMID 与单实例锁
//
// 本文件只保留：路径常量、模块装配、跨模块聚合通道（prefs:get）、应用生命周期。
// 各模块**一律不 require("electron")**，electron 对象在这里注入；纯判定仍集中在
// zoom / window_state / reminders / diagnostics / url_guard（零依赖、CI 的 node
// 自检覆盖，见 ci.yml 的「Electron 主进程自检」步）。

const { app, BrowserWindow, clipboard, dialog, ipcMain, Notification, screen, session, shell } = require("electron");
const os = require("os");
const path = require("path");
const { tFor } = require("./i18n");
const { createLogger } = require("./logger");
const { createBackendProcess } = require("./backend_process");
const { createPrefs } = require("./prefs");
const { createDiagnosticsBridge } = require("./diagnostics_bridge");
const { createNotifications } = require("./notifications");
const { createNavigation } = require("./navigation");
const { createWindowModule } = require("./window");
const { createUpdater } = require("./updater");
const { createSingleInstance } = require("./single_instance");

// 仓库根：web/electron/ 向上两级
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "web", "backend");
const DIST_DIR = path.join(REPO_ROOT, "web", "frontend", "dist");

// ---- 装配（顺序即依赖方向：日志 → 偏好 → 诊断 → 后端 → 提醒 → 导航/窗口 → 更新）----
const { log, logFilePath } = createLogger({ app });

const prefs = createPrefs({ app, log, BrowserWindow, tFor });
const diagnostics = createDiagnosticsBridge({
  app, log, tFor, resolvedLang: prefs.resolvedLang, logFilePath,
  BrowserWindow, dialog, clipboard, shell, os,
});
const backend = createBackendProcess({
  app, log, tFor, notifyUser: diagnostics.notifyUser,
  resolvedLang: prefs.resolvedLang, backendDir: BACKEND_DIR,
});
const notifications = createNotifications({
  app, log, tFor, resolvedLang: prefs.resolvedLang,
  BrowserWindow, Notification, backendPort: backend.BACKEND_PORT,
});
const navigation = createNavigation({ session, shell, log, backendPort: backend.BACKEND_PORT });
const windows = createWindowModule({
  app, BrowserWindow, screen, path, log, tFor, resolvedLang: prefs.resolvedLang,
  backendPort: backend.BACKEND_PORT, distDir: DIST_DIR,
  // 偏好通道的桥。**必须同步登记进 build.files** —— check_packaging.js 也守这一条
  // （漏了的话安装版的通道会缺失）。
  preloadPath: path.join(__dirname, "preload.js"),
  navigation, prefs, notifications, backend,
});
const updater = createUpdater({
  app, log, tFor, resolvedLang: prefs.resolvedLang, dialog,
  stopBackend: backend.stopBackend, notifyUser: diagnostics.notifyUser,
});

// AUMID 与单实例锁必须**在模块加载期同步完成**（窗口/通知都依赖这个时机，
// 见 single_instance.js 顶部的契约）；返回 hasLock 供启动链路决定是否继续。
const single = createSingleInstance({ app, BrowserWindow, log });

// ---- 偏好通道注册（ipcMain.handle 不依赖 ready，装配后立刻注册）----
prefs.registerIpc(ipcMain);
notifications.registerIpc(ipcMain);
diagnostics.registerIpc(ipcMain);

// prefs:get 是**跨模块聚合视图**（偏好 + 到点提醒 + 工作区）：它同时读偏好与提醒
// 两个模块的状态，所以留在装配根组装——模块之间不互相 require（避免环）。
ipcMain.handle("prefs:get", () => {
  const { enabled, days } = notifications.reminderPrefs();
  return {
    ...prefs.snapshot(),
    // 笔 5：到点提醒开关的真值也在这里（它是主进程在发通知）
    reminders: enabled,
    // 「提前几天开始提醒」：设置页给 3/5/7，默认 3
    reminderDays: days,
    workspace: notifications.workspace(),
  };
});

app.whenReady().then(() => {
  if (!single.hasLock) return; // 已请求退出的第二实例：不再拉起后端与窗口
  // 缩放偏好在 ready 后加载：loadFromDisk 走 app.getPath("userData")
  prefs.loadFromDisk();
  navigation.installCsp();

  // 若后端端口已被占用（用户可能已用 start.ps1 起了服务），直接复用
  backend.checkHealth((ok) => {
    if (ok) {
      log("Backend already running — opening the window directly");
      backend.markReady();
      windows.createWindow();
    } else {
      backend.startBackend();
      backend.waitBackendReady(() => windows.createWindow());
    }
  });

  updater.setup();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) windows.createWindow();
  });
});

// 退出时结束后端与提醒定时器（不留常驻的东西）
app.on("before-quit", () => {
  backend.stopBackend();
  notifications.stopTimer();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
