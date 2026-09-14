// 求职工作台 · Electron 主进程
// 职责：探测 Python → 拉起后端 → 等 /api/health 就绪 → 开窗口加载界面
//       → 关闭窗口时结束后端进程。
// 前端静态产物由 FastAPI 同源托管（web/frontend/dist），无需 vite dev server，
// 也无需放宽 CORS —— 页面与 API 同源。

const { app, BrowserWindow, dialog } = require("electron");
const { spawn, execFileSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");
const { tFor } = require("./i18n");

const BACKEND_PORT = 8765;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/api/health`;
const HEARTBEAT_INTERVAL = 500; // ms
const HEARTBEAT_TIMEOUT = 30000; // ms

let backendProcess = null;
let backendReady = false;

// 仓库根：web/electron/ 向上两级
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const BACKEND_DIR = path.join(REPO_ROOT, "web", "backend");
const DIST_DIR = path.join(REPO_ROOT, "web", "frontend", "dist");

function log(msg) {
  const line = `[job-workbench] ${new Date().toISOString()} ${msg}`;
  console.log(line);
  // GUI 模式下 console.log 不可见——落盘到 userData 供用户侧诊断（冒烟实测痛点）
  // 超过 1MB 轮转为 .old，避免无限增长
  try {
    const dir = app.getPath("userData");
    fs.mkdirSync(dir, { recursive: true });
    const lp = path.join(dir, "main.log");
    if (fs.existsSync(lp) && fs.statSync(lp).size > 1024 * 1024) {
      fs.renameSync(lp, `${lp}.old`);
    }
    fs.appendFileSync(lp, `${line}\n`);
  } catch (e) {
    // 日志失败不影响主流程
  }
}

// ---- 界面缩放 -----------------------------------------------------------------
// 此前完全依赖 Electron 默认行为：没有显式实现，也就没有持久化与上下限——
// 「Ctrl+= 能不能用、级别记不记得住」全看版本默认值。这里把它做成确定行为：
//   Ctrl+= / Ctrl+- 以 0.5 级步进（Electron 一级 ≈ ×1.2），Ctrl+0 复位；
//   级别夹在 -3..+3（约 0.58x–1.73x）；写进 userData/zoom.json，重启沿用。
// 触控板的捏合缩放（visual zoom）同时关掉：两套缩放机制并存时，画面会出现
// 「捏合能放大、一刷新又弹回去」的错觉，只保留可记忆的这一套。
// 按键映射与上下限夹取在 zoom.js（纯函数，zoom.test.js 机检，CI 一并跑）。
const { clampLevel, nextLevel } = require("./zoom");

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

// ---- Python 探测（优先级：JOBWS_PYTHON 环境变量 → PATH 中 python → python3）----
function detectPython() {
  const candidates = [];
  if (process.env.JOBWS_PYTHON) {
    candidates.push(process.env.JOBWS_PYTHON);
  }
  // PATH 中的可执行文件（Windows 上 python.exe）
  const whichPython = findOnPath("python");
  if (whichPython) candidates.push(whichPython);
  const whichPython3 = findOnPath("python3");
  if (whichPython3) candidates.push(whichPython3);

  for (const cand of candidates) {
    try {
      // 验证能运行，且含 FastAPI/uvicorn
      const out = execFileSync(cand, ["-c", "import uvicorn, fastapi; print('ok')"], {
        timeout: 10000,
        stdio: "pipe",
      }).toString().trim();
      if (out === "ok") {
        log(`Using Python: ${cand}`);
        return cand;
      }
    } catch (e) {
      log(`Python not usable: ${cand} (${e.message.split("\n")[0]})`);
    }
  }
  return null;
}

function findOnPath(name) {
  const sep = process.platform === "win32" ? ";" : ":";
  const paths = (process.env.PATH || "").split(sep);
  const exts = process.platform === "win32" ? [".exe", ".cmd", ""] : [""];
  for (const p of paths) {
    for (const ext of exts) {
      const candidate = path.join(p, name + ext);
      if (fs.existsSync(candidate)) return candidate;
    }
  }
  return null;
}

// ---- 后端健康检查 ----
// cb 用 done 门保护：timeout 与 error 存在竞态（destroy 后理论可能双触发），
// 双回调会让 waitBackendReady 双轮询、后端就绪时 createWindow 两次 → 双窗口
function checkHealth(cb) {
  let done = false;
  const once = (ok) => {
    if (done) return;
    done = true;
    cb(ok);
  };
  const req = http.get(HEALTH_URL, { timeout: 1000 }, (res) => {
    let body = "";
    res.on("data", (d) => (body += d));
    res.on("end", () => once(res.statusCode === 200 && body.includes("ok")));
  });
  req.on("error", () => once(false));
  req.on("timeout", () => {
    req.destroy();
    once(false);
  });
}

function waitBackendReady(cb) {
  const start = Date.now();
  const poll = () => {
    checkHealth((ok) => {
      if (ok) {
        backendReady = true;
        log("Backend ready");
        cb();
        return;
      }
      if (Date.now() - start > HEARTBEAT_TIMEOUT) {
        log("Backend startup timed out. Packaged builds: see the [backend-err] exit reason above in this log; source runs: check your Python/FastAPI environment");
        app.quit();
        return;
      }
      setTimeout(poll, HEARTBEAT_INTERVAL);
    });
  };
  poll();
}

// ---- 启动后端：优先用打包的 exe，回退 python -m uvicorn ----
function findBackendExe() {
  // 打包形态：electron-builder extraResources 的 resources/backend/。
  // （asar 内不可能有 exe；仓库内构建的 exe 在 web/backend/dist/ 下——
  //   仓库形态本就走 detectPython 回退，此函数只服务打包形态）
  const candidate = path.join(process.resourcesPath, "backend", "job-workbench-backend.exe");
  return fs.existsSync(candidate) ? candidate : null;
}

function startBackend() {
  if (backendProcess) return;

  const exe = findBackendExe();
  if (exe) {
    log(`Using packaged backend: ${exe}`);
    backendProcess = spawn(exe, [], {
      cwd: path.dirname(exe),
      stdio: "pipe",
      detached: false,
    });
  } else {
    const python = detectPython();
    if (!python) {
      log("No packaged backend and no usable Python found (needs FastAPI/uvicorn). Set the JOBWS_PYTHON environment variable to point at one.");
      app.quit();
      return;
    }
    log(`Using python backend: ${python}`);
    backendProcess = spawn(python, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)], {
      cwd: BACKEND_DIR,
      stdio: "pipe",
      detached: false,
    });
  }

  // 转发后端日志到主进程控制台，便于诊断后端启动失败
  backendProcess.stdout.on("data", (d) => log(`[backend] ${d}`));
  backendProcess.stderr.on("data", (d) => log(`[backend-err] ${d}`));

  backendProcess.on("error", (err) => {
    log(`Backend process error: ${err.message}`);
  });
  backendProcess.on("exit", (code) => {
    if (!backendReady && code !== 0) {
      log(`Backend exited unexpectedly, code=${code}`);
    }
    backendProcess = null;
  });
}

function stopBackend() {
  if (!backendProcess) return;
  const pid = backendProcess.pid;
  try {
    if (process.platform === "win32") {
      // taskkill /t 杀进程树，避免 uvicorn/exe 的孙进程变成孤儿（调研确认的坑）
      const { execSync } = require("child_process");
      execSync(`taskkill /pid ${pid} /f /t`, { stdio: "ignore" });
    } else {
      // POSIX：杀进程组
      try {
        process.kill(-pid, "SIGTERM");
      } catch (e) {
        backendProcess.kill("SIGTERM");
      }
    }
  } catch (e) {
    log(`Failed to stop backend: ${e.message}`);
  }
  backendProcess = null;
}

// ---- 创建窗口 ----
// 前端 dist 探测：打包形态下 extraResources 把前端 dist 放进了 resources/backend/dist
// （后端同源托管），仓库形态才是 web/frontend/dist。冒烟实测：只认仓库路径会让打包
// 应用「后端就绪后找不到界面」自退（exit 0）。
function findFrontendDist() {
  const packaged = path.join(process.resourcesPath, "backend", "dist");
  if (fs.existsSync(path.join(packaged, "index.html"))) return packaged;
  return DIST_DIR;
}

function createWindow() {
  const distDir = findFrontendDist();
  if (!fs.existsSync(path.join(distDir, "index.html"))) {
    log(`Frontend build output not found: ${distDir}/index.html`);
    log('Run "npm run build" under web/frontend first');
    app.quit();
    return;
  }

  const win = new BrowserWindow({
    width: 1280,
    height: 880,
    // 初始标题按系统语言：首帧（以及后端没起来、页面加载失败的路径）也得是对的语言。
    // 页面加载完成后由渲染进程的 document.title 接管（见前端 i18n 的 applyDocumentTitle）。
    // 已知取舍：主进程读不到界面里选的语言，只能跟系统语言——理由写在 i18n.js 顶部。
    title: tFor(app.getLocale())("windowTitle"),
    backgroundColor: "#0a0e17",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);

  // 缩放：加载完成后应用已保存的级别（开发时热重载不会丢），快捷键见下
  let zoomLevel = loadZoomLevel();
  const applyZoom = () => win.webContents.setZoomLevel(zoomLevel);
  win.webContents.on("did-finish-load", applyZoom);
  // 该 API 返回 Promise（未就绪/已销毁时会 reject），与文件里其它异步面一样显式兜住
  win.webContents.setVisualZoomLevelLimits(1, 1)
    .catch((e) => log(`Failed to disable visual zoom: ${e.message}`));

  win.webContents.on("before-input-event", (event, input) => {
    // macOS 用 Cmd、其余平台用 Ctrl（发布物目前只有 win64，这一支是为将来留的）；
    // Shift 允许（Ctrl+Shift+= 打出的就是 "+"）
    const mod = process.platform === "darwin" ? input.meta : input.control;
    if (input.type !== "keyDown" || input.alt) return;
    const next = nextLevel(zoomLevel, input.key, mod);
    if (next === null) return;
    // 拦下这次按键：否则默认菜单（View → Zoom In/Out）会对同一次按键再缩一遍
    event.preventDefault();
    if (next === zoomLevel) return;
    zoomLevel = next;
    applyZoom();
    saveZoomLevel(zoomLevel);
    log(`Zoom level: ${zoomLevel}`);
  });

  win.on("closed", () => {
    stopBackend();
  });
}

// ---- 自动更新（electron-updater）----
// 只在打包形态启用：源码运行时没有 app-update.yml，检查必然失败，开发者也不需要它。
//
// 交互刻意做成"两次询问"：先问要不要下载，下载完再问要不要重启。
// 静默下载 + 静默重启是更省事的写法，但会打断用户正在做的事——而这个应用一关窗口
// 后端进程也停，重启的代价比一般桌面应用更高，必须由用户自己挑时机。
function setupAutoUpdate() {
  if (!app.isPackaged) {
    log("Source run — skipping auto-update check");
    return;
  }

  let autoUpdater;
  try {
    ({ autoUpdater } = require("electron-updater"));
  } catch (e) {
    // 依赖没打进包时不该让整个应用起不来——更新只是增强，不是启动必需
    log(`Auto-update unavailable (electron-updater not bundled): ${e.message}`);
    return;
  }

  autoUpdater.autoDownload = false;
  // 用主进程日志接手 updater 的输出：GUI 下看不到控制台，出问题只能靠这个文件
  autoUpdater.logger = { info: log, warn: log, error: log, debug: () => {} };

  autoUpdater.on("error", (err) => log(`Auto-update error: ${(err && err.message) || err}`));
  autoUpdater.on("update-not-available", () => log("Already up to date"));

  autoUpdater.on("update-available", (info) => {
    log(`Update available: ${info.version}`);
    const t = tFor(app.getLocale());
    dialog
      .showMessageBox({
        type: "info",
        title: t("updateAvailableTitle"),
        message: t("updateAvailableMessage", { version: info.version }),
        detail: t("updateAvailableDetail"),
        buttons: [t("updateAvailableDownload"), t("updateAvailableLater")],
        defaultId: 0,
        cancelId: 1,
      })
      .then(({ response }) => {
        if (response !== 0) return;
        log("User chose to download the update");
        autoUpdater.downloadUpdate().catch((e) => log(`Update download failed: ${e.message}`));
      });
  });

  autoUpdater.on("update-downloaded", (info) => {
    log(`Update downloaded: ${info.version}`);
    const t = tFor(app.getLocale());
    dialog
      .showMessageBox({
        type: "info",
        title: t("updateReadyTitle"),
        message: t("updateReadyMessage", { version: info.version }),
        detail: t("updateReadyDetail"),
        buttons: [t("updateReadyRestart"), t("updateReadyInstallOnQuit")],
        defaultId: 0,
        cancelId: 1,
      })
      .then(({ response }) => {
        if (response !== 0) return;
        log("User chose to restart and install");
        stopBackend();
        autoUpdater.quitAndInstall();
      });
  });

  // 延迟检查：让窗口先渲染出来，别和启动链路抢时间
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((e) => log(`Update check failed: ${e.message}`));
  }, 5000);
}

app.whenReady().then(() => {
  // 若后端端口已被占用（用户可能已用 start.ps1 起了服务），直接复用
  checkHealth((ok) => {
    if (ok) {
      log("Backend already running — opening the window directly");
      backendReady = true;
      createWindow();
    } else {
      startBackend();
      waitBackendReady(() => createWindow());
    }
  });

  setupAutoUpdate();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// 退出时结束后端
app.on("before-quit", () => {
  stopBackend();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
