// 求职工作台 · Electron 主进程
// 职责：探测 Python → 拉起后端 → 等 /api/health 就绪 → 开窗口加载界面
//       → 关闭窗口时结束后端进程。
// 前端静态产物由 FastAPI 同源托管（web/frontend/dist），无需 vite dev server，
// 也无需放宽 CORS —— 页面与 API 同源。

const { app, BrowserWindow, dialog, ipcMain, Notification, screen, session, shell } = require("electron");
const { spawn, execFileSync } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");
const { tFor } = require("./i18n");
const { isAllowedNavigation, isSafeExternalUrl } = require("./url_guard");

const BACKEND_PORT = 8765;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/api/health`;
const HEARTBEAT_INTERVAL = 500; // ms
const HEARTBEAT_TIMEOUT = 30000; // ms

// 后端默认「启动后自动用系统浏览器打开界面」（独立运行的 web 形态，见 backend/main.py 的
// _should_open_browser）。桌面端由 Electron 托着窗口，后端再弹一个浏览器就是多开一个界面——
// 必须显式关掉。此前漏传该变量：打包版每次启动，系统浏览器都会跟着冒出来一个。
// 有意覆盖为 "1"（不尊重外部已设的其它取值）：桌面壳托窗口是既定形态，不设例外。
//
// 另注入 JOBWS_APP_VERSION（= app.getVersion()，即 asar 内 package.json 的版本）：
// 设置页「关于」区块显示版本号的数据源，后端 /api/system/paths 读取；开发模式下
// 后端回退读仓库 web/electron/package.json——两路同源同值。做成函数、到真正拉起
// 后端时才求值：避免在模块加载阶段依赖 app 的初始化状态。
function backendEnv() {
  return { ...process.env, JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: app.getVersion() };
}

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
  //
  // **userData 的落点是 %APPDATA%\job-workbench，与 productName 无关**（2026-09-14
  // 实测：productName 还是「求职工作台」时，main.log / zoom.json 就写在这里；Electron
  // 取的是 packaged 的 `name`）。所以 productName 英文化（→ Job Workbench）**不会**
  // 搬动日志、缩放偏好或工作区数据——后端的根也钉在同一个名字上（pathres.py 的
  // `_user_data_dir`，那处是给「数据在哪」用的单一真值源）。要改这个目录名，两处
  // 必须一起改，并且要交代迁移。
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
const { ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, clampLevel, nextLevel, levelToPercent } = require("./zoom");

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
let zoomLevel = 0;          // app ready 时由 loadZoomLevel() 填充（getPath 要求 ready）
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

// 通道注册在模块顶层即可（ipcMain.handle 不依赖 ready）
ipcMain.handle("prefs:get", () => ({
  level: zoomLevel,
  min: ZOOM_MIN,
  max: ZOOM_MAX,
  step: ZOOM_STEP,
  percent: levelToPercent(zoomLevel),
  lang: resolvedLang(),
  // 笔 5：到点提醒开关的真值也在这里（它是主进程在发通知）
  reminders: reminderState.enabled,
  // 「提前几天开始提醒」：设置页给 3/5/7，默认 3
  reminderDays: reminderState.days,
  workspace: reportedWorkspace,
}));

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

ipcMain.handle("prefs:set-zoom", (_event, payload) => {
  const p = payload || {};
  return applyZoomChange(p.level, p.persist !== false);
});

// 与前端 LANGS 同一份口径；不在表里的上报一律忽略（不受信输入不进状态）
const UI_LANGS = ["zh-CN", "en"];

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
        // 同 P2：超时后静默自退，用户看到的是"双击了没反应"
        const t = tFor(resolvedLang());
        notifyUser(
          t("backendTimeoutTitle"),
          `${t("backendTimeoutMessage", { seconds: HEARTBEAT_TIMEOUT / 1000 })}\n\n${HEALTH_URL}`);
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
      env: backendEnv(),
    });
  } else {
    const python = detectPython();
    if (!python) {
      log("No packaged backend and no usable Python found (needs FastAPI/uvicorn). Set the JOBWS_PYTHON environment variable to point at one.");
      // 必须出声（2026-09-23 二轮审计）：此前只写日志就 app.quit()——进程结束时
      // 连 30 秒那条"启动超时"提示都来不及出现，用户看到的就是"双击了没反应"
      const t = tFor(resolvedLang());
      notifyUser(t("backendMissingPythonTitle"), t("backendMissingPythonMessage"));
      app.quit();
      return;
    }
    log(`Using python backend: ${python}`);
    backendProcess = spawn(python, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)], {
      cwd: BACKEND_DIR,
      stdio: "pipe",
      detached: false,
      env: backendEnv(),
    });
  }

  // 转发后端日志到主进程控制台，便于诊断后端启动失败
  backendProcess.stdout.on("data", (d) => log(`[backend] ${d}`));
  backendProcess.stderr.on("data", (d) => log(`[backend-err] ${d}`));

  backendProcess.on("error", (err) => {
    log(`Backend process error: ${err.message}`);
  });
  backendProcess.on("exit", (code) => {
    // 2026-09-23 审计 P2：此前只写日志就静默自退（或窗口停在空白）——用户看到的
    // 是"双击了没反应"，而根因（后端起不来 / 中途崩了）只有打开日志才看得到。
    // 写日志与告诉用户是两件事，都要做。
    const t = tFor(resolvedLang());
    if (!backendReady && code !== 0) {
      log(`Backend exited unexpectedly, code=${code}`);
      notifyUser(t("backendStartFailedTitle"),
                 `${t("backendStartFailedMessage", { code })}\n\n${t("backendStartFailedDetail")}`);
    } else if (backendReady && code) {
      log(`Backend died while running, code=${code}`);
      notifyUser(t("backendDiedTitle"),
                 `${t("backendDiedMessage", { code })}\n\n${t("backendDiedDetail")}`);
    }
    backendProcess = null;
  });
}

/**
 * 给用户一条**看得见**的说明。
 *
 * 为什么单独成函数：窗口可能还没创建（后端没起来正是窗口创建不了的原因），
 * 那时 `dialog.showMessageBox` 没有父窗口可用；而 `showErrorBox` 不依赖窗口。
 * 顺序上"有窗口就挂窗口、没有就直接弹"，两条路都要能出声。
 */
function notifyUser(title, message) {
  try {
    const win = BrowserWindow.getAllWindows()[0];
    if (win) {
      dialog.showMessageBox(win, { type: "error", title, message, buttons: ["OK"] });
    } else {
      dialog.showErrorBox(title, message);
    }
  } catch (e) {
    // 通知失败不该变成第二次崩溃：日志里留一句即可
    log(`notifyUser failed: ${e.message}`);
  }
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

// ---- 窗口位置与尺寸记忆 ---------------------------------------------------------
// 此前建窗尺寸硬编码 1280×880，也没记位置：每次开窗都要重摆。落点与缩放偏好同款
// （userData/window-state.json，两处都在 %APPDATA%\job-workbench）。
//
// 落盘用 getNormalBounds()：最大化/全屏时 getBounds() 给的是"铺满后"的矩形，存下去
// 会让下次开窗直接铺满——那不是用户的意思。判定（夹取到某块屏、拔屏后回落居中、
// 坏文件容错）全在 window_state.js，纯函数、有单测、CI 一起跑。
const {
  clampToWorkArea,
  parseState,
  serializeState,
  MIN_WIDTH,
  MIN_HEIGHT,
} = require("./window_state");

const WINDOW_STATE_SAVE_DELAY = 400; // ms：拖动/缩放过程中只在停手后落盘
let windowStateTimer = null;

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

// ---- 到点提醒（笔 5）------------------------------------------------------------
// 「面试 / 下次动作到期」的最小形态：窗口就绪后与运行期内每 6 小时问一次后端
// `/api/reminders/due`，够条件就发一条系统通知（同一天只提醒一次）。
//
// **不做常驻、不建托盘**：关窗即停，与「无后台路径」这条红线一致——本地优先的工具不该在
// 用户以为已经退出之后还留着东西跑。判定（该不该提醒 / 正文怎么排）全在 reminders.js，
// 纯函数、有单测、CI 跑。
const {
  buildNotification,
  dueItems,
  nextState,
  shouldNotify,
  todayKey,
} = require("./reminders");

const REMINDER_CHECK_INTERVAL = 6 * 60 * 60 * 1000; // 6 小时
// 「提前几天开始提醒」的默认值与上限：设置页给 3/5/7，主进程按 state.days 带查询参数
const REMINDER_DAYS_DEFAULT = 3;
const REMINDER_DAYS_MAX = 30;
let reminderState = { enabled: true, days: REMINDER_DAYS_DEFAULT, notified: {} };
let reminderTimer = null;
// 渲染进程上报的当前工作区（真值在它的 localStorage 里）：不报就按后端默认工作区查
let reportedWorkspace = "";

function remindersPath() {
  return path.join(app.getPath("userData"), "reminders.json");
}

function loadReminders() {
  try {
    const data = JSON.parse(fs.readFileSync(remindersPath(), "utf-8"));
    reminderState = {
      enabled: data.enabled !== false,
      days: Number(data.days) || REMINDER_DAYS_DEFAULT,
      // 旧状态文件里只有 lastNotified（"哪天提醒过"）：按"每事项每天一次"的新口径
      // 它没有意义，直接丢弃——最坏情况是升级当天再报一次，比漏报轻。
      notified: data.notified && typeof data.notified === "object" ? data.notified : {},
    };
  } catch (e) {
    // 首次运行没有这个文件；文件损坏也按默认（开着、今天没提醒过）处理
    reminderState = { enabled: true, days: REMINDER_DAYS_DEFAULT, notified: {} };
  }
}

function saveReminders() {
  try {
    fs.mkdirSync(path.dirname(remindersPath()), { recursive: true });
    fs.writeFileSync(remindersPath(), JSON.stringify(reminderState, null, 2));
  } catch (e) {
    log(`Failed to persist reminder state: ${e.message}`);
  }
}

function showDueNotification(payload) {
  const t = tFor(resolvedLang());
  const { title, body } = buildNotification(t, payload);
  const notification = new Notification({ title, body });
  // 点通知就把窗口拉到前面，并把"最该看的那条"交给界面
  // （前端据此跳到追踪表并展开它——落地在 `drillToApplication` 那条既有链路）
  notification.on("click", () => {
    const win = BrowserWindow.getAllWindows()[0];
    if (win) {
      win.show();
      win.focus();
      const first = dueItems(payload)[0];
      const id = first && first.item ? first.item.id : "";
      if (id) win.webContents.send("reminder:focus", { id });
    }
  });
  notification.show();
  reminderState = nextState(reminderState, todayKey(), payload);
  saveReminders();
  log(`Reminder shown: ${body.split("\n").length} line(s)`);
}

function checkReminders() {
  if (!reminderState.enabled) return;
  const params = new URLSearchParams();
  if (reportedWorkspace) params.set("ws", reportedWorkspace);
  // 「提前几天」由设置项决定（后端默认 3）：它只影响"待办"这一类
  params.set("days", String(reminderState.days || REMINDER_DAYS_DEFAULT));
  const req = http.get(
    `http://127.0.0.1:${BACKEND_PORT}/api/reminders/due?${params.toString()}`,
    { timeout: 4000 },
    (res) => {
      let body = "";
      res.on("data", (chunk) => (body += chunk));
      res.on("end", () => {
        if (res.statusCode !== 200) return;
        let payload;
        try {
          payload = JSON.parse(body);
        } catch (e) {
          return; // 坏响应既不发通知也不抛：提醒是增强，不是启动必需
        }
        if (shouldNotify(reminderState, todayKey(), payload)) showDueNotification(payload);
      });
    }
  );
  // 后端还没起来（窗口正等健康检查）是常态：静默跳过，等下一个周期
  req.on("error", () => {});
  req.on("timeout", () => req.destroy());
}

/** 幂等：窗口加载完成时调用；重复调用只保留一个定时器。 */
function startReminders() {
  if (reminderTimer) return;
  loadReminders();
  checkReminders();
  reminderTimer = setInterval(checkReminders, REMINDER_CHECK_INTERVAL);
}

function stopReminders() {
  if (!reminderTimer) return;
  clearInterval(reminderTimer);
  reminderTimer = null;
}

ipcMain.handle("prefs:set-workspace", (_event, ws) => {
  reportedWorkspace = String(ws || "").trim();
  log(`Workspace reported by renderer: ${reportedWorkspace || "(default)"}`);
  return { workspace: reportedWorkspace };
});

ipcMain.handle("prefs:set-reminders", (_event, value) => {
  // 兼容两种调用：布尔（旧调用点）与 `{ enabled?, days? }`（设置页的开关 + 提前天数）
  const patch = value && typeof value === "object" ? value : { enabled: value };
  if (typeof patch.enabled === "boolean") reminderState.enabled = patch.enabled;
  const days = Number(patch.days);
  if (Number.isFinite(days)) {
    reminderState.days = Math.max(1, Math.min(Math.round(days), REMINDER_DAYS_MAX));
  }
  saveReminders();
  // 打开或改天数后立刻看一眼，而不是等到下一个周期——按下开关/改完天数时想看到的是"现在就生效"
  if (reminderState.enabled) checkReminders();
  return { reminders: reminderState.enabled, reminderDays: reminderState.days };
});

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
      preload: path.join(__dirname, "preload.js"),
    },
  });
  win.setMenuBarVisibility(false);
  // 记住位置尺寸：拖动/缩放去抖落盘，关窗时立即落盘（与 zoom.json 同款"偏好留痕"）
  trackWindowState(win);
  // 只允许留在本机界面：页面一旦被导航到外部站点，preload 注入的偏好通道也会跟着
  // 暴露给那个文档（contextBridge 是按文档注入的）。窗口内的外链交给系统浏览器。
  // 判断收敛到 url_guard.js（审计 P0-2）：前缀匹配会被 `127.0.0.1:8765.evil.com`
  // 绕过，外链必须有 scheme 白名单（只放行 https）。
  const allowedOrigin = `http://127.0.0.1:${BACKEND_PORT}`;
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAllowedNavigation(url, allowedOrigin)) {
      event.preventDefault();
      log(`Blocked navigation to ${url}`);
    }
  });
  // 服务端 302 不走 will-navigate，走的是独立的可取消事件（批末审查发现漏挂）。
  // 本机后端是唯一可能发重定向的一方，但守卫的语义就是"所有导航出口都要判"。
  win.webContents.on("will-redirect", (event, url) => {
    if (!isAllowedNavigation(url, allowedOrigin)) {
      event.preventDefault();
      log(`Blocked redirect to ${url}`);
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (!isSafeExternalUrl(url)) {
      log(`Blocked external open of ${url}`);
      return { action: "deny" };
    }
    shell.openExternal(url).catch((e) => log(`Failed to open external URL: ${e.message}`));
    return { action: "deny" };
  });
  win.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);

  // 缩放级别在 app ready 时已加载（见 whenReady）；这里把当前值应用到新窗口
  const applyZoom = () => win.webContents.setZoomLevel(zoomLevel);
  win.webContents.on("did-finish-load", () => {
    applyZoom();
    // 到点提醒：界面出来后问一次（此时后端已就绪），之后每 6 小时一次
    startReminders();
  });
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
    applyZoomChange(next, true);   // 与设置页滑块共用同一个写入口
    log(`Zoom level: ${zoomLevel}`);
  });

  win.on("closed", () => {
    stopBackend();
    // 「关窗即停」要字面成立：macOS 上 window-all-closed 不退出进程，只靠 before-quit
    // 会让提醒定时器继续跑（批末审查）
    stopReminders();
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

  // P2：更新失败此前只进日志——用户既不知道有新版，也不知道检查失败。
  // 不弹窗打断（更新是增强，不是必需），但要在控制台之外给一句可读的结论。
  autoUpdater.on("error", (err) => {
    const reason = (err && err.message) || String(err);
    log(`Auto-update error: ${reason}`);
    const t = tFor(resolvedLang());
    notifyUser(t("updateFailedTitle"), `${t("updateFailedMessage")}\n\n${reason}`);
  });
  autoUpdater.on("update-not-available", () => log("Already up to date"));

  autoUpdater.on("update-available", (info) => {
    log(`Update available: ${info.version}`);
    const t = tFor(resolvedLang());
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
    const t = tFor(resolvedLang());
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
        // 必须静默装（isSilent=true）：安装器已改为向导式（#82），不带这个参数的话
        // 更新会弹出安装向导，把「无感升级」变成「再走一遍安装流程」——而向导里的
        // 默认目录未必等于当前安装目录，用户随手改路径就会产生第二份安装。
        // isForceRunAfter=true：装完自动把应用重新拉起来。
        autoUpdater.quitAndInstall(true, true);
      });
  });

  // 延迟检查：让窗口先渲染出来，别和启动链路抢时间
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((e) => log(`Update check failed: ${e.message}`));
  }, 5000);
}

// 内容安全策略（2026-09-23 二轮审计的纵深防御项）：界面会内联预览**工作区里手写的
// 简历模板 HTML**，没有 CSP 时它一旦被 popup / 重定向绕过窗口守卫，就能以同源身份
// 调本机 API 读写整个工作区（本地 API 无鉴权）。这里只给本机后端这一个源加，
// 且保留 `'unsafe-inline'`：index.html 有一段防闪白用的内联主题引导脚本，
// 去掉它首帧会闪一次默认色（取舍写在 CONTRIBUTING 的「刻意不做」里）。
const CONTENT_SECURITY_POLICY = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "frame-src 'self' blob: data:",
  "object-src 'none'",
  "base-uri 'none'",
].join("; ");

function installContentSecurityPolicy() {
  try {
    session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
      const headers = Object.assign({}, details.responseHeaders);
      if (details.url.startsWith(`http://127.0.0.1:${BACKEND_PORT}`)) {
        headers["Content-Security-Policy"] = [CONTENT_SECURITY_POLICY];
      }
      callback({ responseHeaders: headers });
    });
  } catch (e) {
    // 加固失败不该挡住启动：日志里留一条，界面照常
    log(`CSP install failed: ${e.message}`);
  }
}

app.whenReady().then(() => {
  // 缩放偏好在 ready 后加载：loadZoomLevel 走 app.getPath("userData")
  zoomLevel = loadZoomLevel();
  installContentSecurityPolicy();

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

// 退出时结束后端与提醒定时器（不留常驻的东西）
app.on("before-quit", () => {
  stopBackend();
  stopReminders();
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
