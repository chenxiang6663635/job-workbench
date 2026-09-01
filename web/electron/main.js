// 求职工作台 · Electron 主进程
// 职责：探测 Python → 拉起后端 → 等 /api/health 就绪 → 开窗口加载界面
//       → 关闭窗口时结束后端进程。
// 前端静态产物由 FastAPI 同源托管（web/frontend/dist），无需 vite dev server，
// 也无需放宽 CORS —— 页面与 API 同源。

const { app, BrowserWindow } = require("electron");
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
  console.log(`[job-workbench] ${msg}`);
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
function checkHealth(cb) {
  const req = http.get(HEALTH_URL, { timeout: 1000 }, (res) => {
    let body = "";
    res.on("data", (d) => (body += d));
    res.on("end", () => {
      const ok = res.statusCode === 200 && body.includes("ok");
      cb(ok);
    });
  });
  req.on("error", () => cb(false));
  req.on("timeout", () => {
    req.destroy();
    cb(false);
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
        log("后端启动超时，请检查 Python/FastAPI 环境");
        app.quit();
        return;
      }
      setTimeout(poll, HEARTBEAT_INTERVAL);
    });
  };
  poll();
}

// ---- 启动后端 ----
function startBackend() {
  if (backendProcess) return;

  const python = detectPython();
  if (!python) {
    log("未找到可用的 Python（需含 FastAPI/uvicorn）。可用 JOBWS_PYTHON 环境变量指定。");
    app.quit();
    return;
  }

  backendProcess = spawn(python, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)], {
    cwd: BACKEND_DIR,
    stdio: "pipe",
    detached: false,
  });

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
  if (backendProcess) {
    try {
      backendProcess.kill();
    } catch (e) {
      log(`结束后端失败: ${e.message}`);
    }
    backendProcess = null;
  }
}

// ---- 创建窗口 ----
function createWindow() {
  if (!fs.existsSync(path.join(DIST_DIR, "index.html"))) {
    log(`未找到前端构建产物 ${DIST_DIR}/index.html`);
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
