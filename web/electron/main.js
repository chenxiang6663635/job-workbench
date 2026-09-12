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
        log(`使用 Python: ${cand}`);
        return cand;
      }
    } catch (e) {
      log(`Python 不可用: ${cand} (${e.message.split("\n")[0]})`);
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
        log("后端已就绪");
        cb();
        return;
      }
      if (Date.now() - start > HEARTBEAT_TIMEOUT) {
        log("后端启动超时。打包版请查看本日志上方 [backend-err] 的退出原因；源码版请检查 Python/FastAPI 环境");
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
    log(`使用打包后端: ${exe}`);
    backendProcess = spawn(exe, [], {
      cwd: path.dirname(exe),
      stdio: "pipe",
      detached: false,
    });
  } else {
    const python = detectPython();
    if (!python) {
      log("未找到打包后端，也未找到可用的 Python（需含 FastAPI/uvicorn）。可用 JOBWS_PYTHON 环境变量指定。");
      app.quit();
      return;
    }
    log(`使用 python 后端: ${python}`);
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
    log(`后端进程错误: ${err.message}`);
  });
  backendProcess.on("exit", (code) => {
    if (!backendReady && code !== 0) {
      log(`后端意外退出 code=${code}`);
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
    log(`结束后端失败: ${e.message}`);
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
    log(`未找到前端构建产物 ${distDir}/index.html`);
    log("请先在 web/frontend 下执行 npm run build");
    app.quit();
    return;
  }

  const win = new BrowserWindow({
    width: 1280,
    height: 880,
    title: "求职工作台",
    backgroundColor: "#0a0e17",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setMenuBarVisibility(false);
  win.loadURL(`http://127.0.0.1:${BACKEND_PORT}`);

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
    log("源码形态，跳过自动更新检查");
    return;
  }

  let autoUpdater;
  try {
    ({ autoUpdater } = require("electron-updater"));
  } catch (e) {
    // 依赖没打进包时不该让整个应用起不来——更新只是增强，不是启动必需
    log(`自动更新不可用（electron-updater 未随包分发）: ${e.message}`);
    return;
  }

  autoUpdater.autoDownload = false;
  // 用主进程日志接手 updater 的输出：GUI 下看不到控制台，出问题只能靠这个文件
  autoUpdater.logger = { info: log, warn: log, error: log, debug: () => {} };

  autoUpdater.on("error", (err) => log(`自动更新出错: ${(err && err.message) || err}`));
  autoUpdater.on("update-not-available", () => log("已是最新版本"));

  autoUpdater.on("update-available", (info) => {
    log(`发现新版本 ${info.version}`);
    dialog
      .showMessageBox({
        type: "info",
        title: "有新版本",
        message: `求职工作台 ${info.version} 可用`,
        detail: "下载完成后会再问你要不要重启。现在下载不会打断你正在做的事。",
        buttons: ["下载更新", "以后再说"],
        defaultId: 0,
        cancelId: 1,
      })
      .then(({ response }) => {
        if (response !== 0) return;
        log("用户同意下载更新");
        autoUpdater.downloadUpdate().catch((e) => log(`下载更新失败: ${e.message}`));
      });
  });

  autoUpdater.on("update-downloaded", (info) => {
    log(`更新已下载 ${info.version}`);
    dialog
      .showMessageBox({
        type: "info",
        title: "更新已就绪",
        message: `求职工作台 ${info.version} 已下载完成`,
        detail: "立即重启会先结束后端进程，再安装新版本。",
        buttons: ["立即重启并安装", "退出时再装"],
        defaultId: 0,
        cancelId: 1,
      })
      .then(({ response }) => {
        if (response !== 0) return;
        log("用户同意重启安装");
        stopBackend();
        autoUpdater.quitAndInstall();
      });
  });

  // 延迟检查：让窗口先渲染出来，别和启动链路抢时间
  setTimeout(() => {
    autoUpdater.checkForUpdates().catch((e) => log(`检查更新失败: ${e.message}`));
  }, 5000);
}

app.whenReady().then(() => {
  // 若后端端口已被占用（用户可能已用 start.ps1 起了服务），直接复用
  checkHealth((ok) => {
    if (ok) {
      log("检测到后端已在运行，直接打开界面");
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
