// 界面偏好通道：界面缩放（zoom.json 持久化 + 原生层 setZoomLevel）与界面语言
// （渲染进程上报 + 窗口标题 / 更新对话框取词）的单一真值都收在这里。
// 从 main.js 原样拆出（#204，行为零变更）：
//   * 本模块不 require("electron")——app / BrowserWindow / tFor 由 createPrefs 注入，
//     ipcMain 由 registerIpc(ipcMain) 传入，fs / path / platform 可注入（供测试）；
//   * prefs:get 不在这里：它还要聚合到点提醒与工作区状态，留在 main.js 组装，
//     由 snapshot() 提供偏好字段；
//   * 缩放纯逻辑（夹取 / 按键映射 / 百分比）在 zoom.js，这里只做状态与副作用。
const { ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, clampLevel, nextLevel, levelToPercent } = require("./zoom");

function createPrefs({ app, log, BrowserWindow, tFor, fs = require("fs"), path = require("path"), platform = process.platform }) {
  // ---- 界面缩放 -----------------------------------------------------------------
  // 此前完全依赖 Electron 默认行为：没有显式实现，也就没有持久化与上下限——
  // 「Ctrl+= 能不能用、级别记不记得住」全看版本默认值。这里把它做成确定行为：
  //   Ctrl+= / Ctrl+- 以 0.5 级步进（Electron 一级 ≈ ×1.2），Ctrl+0 复位；
  //   级别夹在 -3..+3（约 0.58x–1.73x）；写进 userData/zoom.json，重启沿用。
  // 触控板的捏合缩放（visual zoom）同时关掉：两套缩放机制并存时，画面会出现
  // 「捏合能放大、一刷新又弹回去」的错觉，只保留可记忆的这一套。
  // 按键映射与上下限夹取在 zoom.js（纯函数，zoom.test.js 机检，CI 一并跑）。
  function zoomStatePath() {
    return path.join(app.getPath("userData"), "zoom.json");
  }

  function loadZoomLevel() {
    try {
      return clampLevel(JSON.parse(fs.readFileSync(zoomStatePath(), "utf-8")).level);
    } catch (e) {
      // 首次运行没有这个文件；文件损坏也按默认级别处理——缩放偏好不值得打断启动
    }
    return 0;
  }

  function saveZoomLevel(level) {
    try {
      fs.mkdirSync(path.dirname(zoomStatePath()), { recursive: true });
      fs.writeFileSync(zoomStatePath(), JSON.stringify({ level }, null, 2));
    } catch (e) {
      log(`Failed to persist zoom level: ${e.message}`);
    }
  }

  // ---- 偏好通道：单一真值在主进程 -------------------------------------------------
  // 「界面大小」与「界面语言」两项偏好由主进程持有（缩放要驱动原生层 setZoomLevel、
  // 语言要渲染窗口标题与更新对话框），渲染进程经 preload 只表达意图。两个入口
  // （设置页滑块、Ctrl± 快捷键）都只写这里，避免各算一套（2026-09-14 #84/#77）。
  let zoomLevel = 0;          // app ready 时由 loadFromDisk() 填充（getPath 要求 ready）
  let currentLang = null;     // 界面语言上报值；未上报前回退系统语言（与旧行为一致）

  /** 当前生效语言：界面语言优先，未上报时按系统语言。 */
  function resolvedLang() {
    return currentLang || app.getLocale();
  }

  function applyZoomToAll() {
    for (const w of BrowserWindow.getAllWindows()) w.webContents.setZoomLevel(zoomLevel);
  }

  /** 把当前缩放广播给所有窗口：设置页滑块据此跟随快捷键造成的变更。 */
  function broadcastZoom() {
    const payload = { level: zoomLevel, percent: levelToPercent(zoomLevel) };
    for (const w of BrowserWindow.getAllWindows()) w.webContents.send("prefs:zoom-changed", payload);
  }

  // 缩放变更的唯一写入口：快捷键与设置页滑块都走这里（夹取 → 应用 → 可选落盘/广播）。
  // persist=false 只用于滑块拖动中的实时预览：不落盘、不广播（广播会把"预览值"当成
  // 最终值回灌，拖动中反而互相打架）；松手时以 persist=true 再调一次。**默认落盘**——
  // 只有显式 false 才是预览，避免调用方传 0/null 之类把状态卡在"永不确认"。
  function applyZoomChange(level, persist) {
    const next = clampLevel(level);   // 夹取只认 zoom.js 这一份实现
    if (next === zoomLevel) return { level: zoomLevel, percent: levelToPercent(zoomLevel) };
    zoomLevel = next;
    applyZoomToAll();
    if (persist) {
      saveZoomLevel(zoomLevel);
      broadcastZoom();
    }
    return { level: zoomLevel, percent: levelToPercent(zoomLevel) };
  }

  // 与前端 LANGS 同一份口径；不在表里的上报一律忽略（不受信输入不进状态）
  const UI_LANGS = ["zh-CN", "en"];

  // 偏好通道的注册（ipcMain.handle 不依赖 ready，实例创建后显式调用即可）。
  // ipcMain 由调用方传入：本模块不 require("electron")，测试里同样传替身。
  function registerIpc(ipcMain) {
    if (!ipcMain) {
      throw new Error("registerIpc(ipcMain) needs Electron's ipcMain: prefs.js never requires electron");
    }

    ipcMain.handle("prefs:set-zoom", (_event, payload) => {
      const p = payload || {};
      return applyZoomChange(p.level, p.persist !== false);
    });

    ipcMain.handle("prefs:set-lang", (_event, lang) => {
      const next = String(lang || "");
      if (!UI_LANGS.includes(next)) {
        log(`Ignored unknown UI language report: ${next}`);
        return { lang: resolvedLang() };
      }
      if (next === currentLang) return { lang: currentLang };
      currentLang = next;
      // 窗口标题只在"页面接管前"有意义（加载完成后由渲染进程的 document.title 接管，
      // 见前端 i18n 的 applyDocumentTitle）；真正随界面语言变的是更新对话框的取词语言。
      const t = tFor(currentLang);
      for (const w of BrowserWindow.getAllWindows()) w.setTitle(t("windowTitle"));
      log(`UI language reported by renderer: ${currentLang}`);
      return { lang: currentLang };
    });
  }

  /** prefs:get 的偏好部分（到点提醒与工作区字段由 main.js 在组装时补齐）。 */
  function snapshot() {
    return {
      level: zoomLevel,
      min: ZOOM_MIN,
      max: ZOOM_MAX,
      step: ZOOM_STEP,
      percent: levelToPercent(zoomLevel),
      lang: resolvedLang(),
    };
  }

  // did-finish-load：缩放级别在 app ready 时已加载（见 loadFromDisk）；
  // 这里把当前值应用到新窗口——只 setZoomLevel，不广播。
  function applyZoomToWindow(win) {
    win.webContents.setZoomLevel(zoomLevel);
  }

  /** before-input-event：Ctrl/Cmd ±/0 → nextLevel → applyZoomChange(next, true)。 */
  function attachZoomShortcuts(win) {
    win.webContents.on("before-input-event", (event, input) => {
      // macOS 用 Cmd、其余平台用 Ctrl（发布物目前只有 win64，这一支是为将来留的）；
      // Shift 允许（Ctrl+Shift+= 打出的就是 "+"）
      const mod = platform === "darwin" ? input.meta : input.control;
      if (input.type !== "keyDown" || input.alt) return;
      const next = nextLevel(zoomLevel, input.key, mod);
      if (next === null) return;
      // 拦下这次按键：否则默认菜单（View → Zoom In/Out）会对同一次按键再缩一遍
      event.preventDefault();
      if (next === zoomLevel) return;
      applyZoomChange(next, true);   // 与设置页滑块共用同一个写入口
      log(`Zoom level: ${zoomLevel}`);
    });
  }

  /** whenReady 时调用：zoomLevel = loadZoomLevel()（getPath 要求 ready）。 */
  function loadFromDisk() {
    zoomLevel = loadZoomLevel();
  }

  function getZoomLevel() {
    return zoomLevel;
  }

  return {
    loadFromDisk,
    registerIpc,
    resolvedLang,
    getZoomLevel,
    snapshot,
    applyZoomToAll,
    broadcastZoom,
    applyZoomChange,
    applyZoomToWindow,
    attachZoomShortcuts,
  };
}

module.exports = { createPrefs };
