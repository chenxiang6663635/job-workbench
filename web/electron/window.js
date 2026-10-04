// 窗口模块（#204 拆分 D）：窗口位置尺寸记忆（window-state.json）+ 建窗。
// 行为逐条对应 main.js 的「窗口位置与尺寸记忆」与「创建窗口」两段：落盘用
// getNormalBounds()、去抖 400ms、关窗立即落盘；建窗时上次状态按当前显示器夹取；
// 三处导航接线交给 navigation.wireWindow；缩放 / 提醒 / 后端生命周期由注入的
// prefs / notifications / backend 承担。
//
// 不 require("electron")：app / BrowserWindow / screen 全部注入；窗口状态的纯判定
// 在 window_state.js（有单测）。本模块只做接线，纯 node 下可安全加载。

const WINDOW_STATE_SAVE_DELAY = 400; // ms：拖动/缩放过程中只在停手后落盘

function createWindowModule({
  app, BrowserWindow, screen, path, fs = require("fs"), log, tFor, resolvedLang,
  backendPort, distDir, preloadPath,
  resourcesPath = process.resourcesPath, platform = process.platform,
  windowState = require("./window_state"),
  navigation, prefs, notifications, backend,
}) {
  const { clampToWorkArea, parseState, serializeState, MIN_WIDTH, MIN_HEIGHT } = windowState;

  // windowStateTimer 是全局单例：去抖定时器被所有窗口共享（任一窗口 close 都会清掉
  // 共享定时器）——与 main.js 原实现一致，不要改成"每窗一份"。
  let windowStateTimer = null;

  // ---- 窗口位置与尺寸记忆 ---------------------------------------------------------
  // 此前建窗尺寸硬编码 1280×880，也没记位置：每次开窗都要重摆。落点与缩放偏好同款
  // （userData/window-state.json，两处都在 %APPDATA%\job-workbench）。
  //
  // 落盘用 getNormalBounds()：最大化/全屏时 getBounds() 给的是"铺满后"的矩形，存下去
  // 会让下次开窗直接铺满——那不是用户的意思。判定（夹取到某块屏、拔屏后回落居中、
  // 坏文件容错）全在 window_state.js，纯函数、有单测、CI 一起跑。
  function windowStatePath() {
    return path.join(app.getPath("userData"), "window-state.json");
  }

  function loadWindowState() {
    try {
      return parseState(fs.readFileSync(windowStatePath(), "utf-8"));
    } catch (e) {
      // 首次运行没有这个文件；文件损坏也按"没有记录"处理——窗口位置不值得打断启动
    }
    return null;
  }

  function saveWindowState(bounds) {
    const text = serializeState(bounds);
    if (!text) return;
    try {
      fs.mkdirSync(path.dirname(windowStatePath()), { recursive: true });
      fs.writeFileSync(windowStatePath(), text);
    } catch (e) {
      log(`Failed to persist window state: ${e.message}`);
    }
  }

  /** 拖动/缩放去抖落盘；关窗时立即落盘（否则最后一次移动会丢）。 */
  function trackWindowState(win) {
    const persist = () => {
      if (win.isDestroyed()) return;
      // getNormalBounds() 自 Electron 6 起就有（本项目锁 ^44）：最大化/全屏时它给的是"还原后"
      // 的矩形，getBounds() 给的是铺满的——存后者会让下次开窗直接铺满。不做能力探测：
      // 那条回落分支永不可达，留着会让读者以为还有第二道保险（批末审查）。
      saveWindowState(win.getNormalBounds());
    };
    const schedule = () => {
      if (windowStateTimer) clearTimeout(windowStateTimer);
      windowStateTimer = setTimeout(() => {
        windowStateTimer = null;
        persist();
      }, WINDOW_STATE_SAVE_DELAY);
    };
    win.on("resize", schedule);
    win.on("move", schedule);
    win.on("close", () => {
      if (windowStateTimer) {
        clearTimeout(windowStateTimer);
        windowStateTimer = null;
      }
      persist();
    });
  }

  /**
   * 建窗用的位置尺寸：上次状态按**当前**显示器夹取（拔掉副屏后不会跑到屏幕外）。
   *
   * 主屏必须排在数组首位：`clampToWorkArea` 的"回落到主屏居中"用的是 `areas[0]`，而
   * `screen.getAllDisplays()` 不保证主屏在前（批末审查）。
   */
  function restoredWindowBounds() {
    const primary = screen.getPrimaryDisplay().workArea;
    const others = screen.getAllDisplays()
      .map((display) => display.workArea)
      .filter((area) => area.x !== primary.x || area.y !== primary.y);
    return clampToWorkArea(loadWindowState(), [primary, ...others]);
  }

  // ---- 创建窗口 -------------------------------------------------------------------
  // 前端 dist 探测：打包形态下 extraResources 把前端 dist 放进了 resources/backend/dist
  // （后端同源托管），仓库形态才是 web/frontend/dist。冒烟实测：只认仓库路径会让打包
  // 应用「后端就绪后找不到界面」自退（exit 0）。
  function findFrontendDist() {
    const packaged = path.join(resourcesPath, "backend", "dist");
    if (fs.existsSync(path.join(packaged, "index.html"))) return packaged;
    return distDir;
  }

  function createWindow() {
    const activeDistDir = findFrontendDist();
    if (!fs.existsSync(path.join(activeDistDir, "index.html"))) {
      log(`Frontend build output not found: ${activeDistDir}/index.html`);
      log('Run "npm run build" under web/frontend first');
      app.quit();
      return;
    }

    // 位置尺寸：上次关窗时的状态，按当前显示器工作区夹取（见 restoredWindowBounds）。
    // 下限取 min(常量, 实际宽高)：屏比下限还窄时（小屏 VM / 高缩放）以屏为准，
    // 否则 BrowserWindow 的 minWidth 会把窗口撑得比屏幕还宽（批末审查）。
    const bounds = restoredWindowBounds();
    const win = new BrowserWindow({
      ...bounds,
      minWidth: Math.min(MIN_WIDTH, bounds.width),
      minHeight: Math.min(MIN_HEIGHT, bounds.height),
      // 初始标题：优先用渲染进程上报过的界面语言，没有则按系统语言。首帧（以及后端
      // 没起来、页面加载失败的路径）也得是对的语言；页面加载完成后由渲染进程的
      // document.title 接管（见前端 i18n 的 applyDocumentTitle）。
      title: tFor(resolvedLang())("windowTitle"),
      backgroundColor: "#0a0e17",
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        // 偏好通道的桥（界面大小 / 界面语言）。**必须同步登记进 build.files** —
        // check_packaging.js 也守这一条（漏了的话安装版的通道会缺失）。
        preload: preloadPath,
      },
    });
    win.setMenuBarVisibility(false);
    // 记住位置尺寸：拖动/缩放去抖落盘，关窗时立即落盘（与 zoom.json 同款"偏好留痕"）
    trackWindowState(win);
    // 导航守卫三处接线（will-navigate / will-redirect / setWindowOpenHandler）收敛在
    // navigation.js（审计 P0-2 的 origin 严格比对与 https 外链白名单）
    navigation.wireWindow(win);
    win.loadURL(`http://127.0.0.1:${backendPort}`);

    // 缩放级别在 app ready 时已由偏好通道加载；这里把当前值应用到新窗口
    win.webContents.on("did-finish-load", () => {
      prefs.applyZoomToWindow(win);
      // 到点提醒：界面出来后问一次（此时后端已就绪），之后每 6 小时一次
      notifications.startTimer();
    });
    // 该 API 返回 Promise（未就绪/已销毁时会 reject），与文件里其它异步面一样显式兜住
    win.webContents.setVisualZoomLevelLimits(1, 1)
      .catch((e) => log(`Failed to disable visual zoom: ${e.message}`));

    // 缩放快捷键（Ctrl+= / Ctrl+- / Ctrl+0）：按键映射、拦默认菜单、落盘与广播
    // 全在偏好通道实现（原 main.js 的 before-input-event 内联逻辑已搬进 prefs）
    prefs.attachZoomShortcuts(win);

    win.on("closed", () => {
      backend.stopBackend();
      // 「关窗即停」要字面成立：macOS 上 window-all-closed 不退出进程，只靠 before-quit
      // 会让提醒定时器继续跑（批末审查）
      notifications.stopTimer();
    });
  }

  return { findFrontendDist, createWindow };
}

module.exports = { createWindowModule };
