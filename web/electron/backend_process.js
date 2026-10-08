// 求职工作台 · 后端进程管理（探测 Python → 拉起后端 → 健康检查 → 停止）。
//
// 从 main.js 原样搬出（#204 主进程拆分），行为零变更；electron 的 app 与其它主进程
// 设施（log / notifyUser / tFor / resolvedLang）全部经 deps 注入，本文件不
// require("electron")——可被 node 直接跑（见 backend_process.test.js）。
//
// 搬运时必须保持的不变量（改动前先回 main.js 对照）：
//   - backendReady 从不复位；
//   - backendStopping 先置位再杀（exit 回调据它把「自杀」与「崩溃」分开）；
//   - startBackend / stopBackend 的空守卫；
//   - exit 三分支与提示文案、日志文案逐字一致；
//   - 面向用户的字符串与日志一律英文（i18n 硬编码检查会拦中文串）。

const BACKEND_PORT = 8765;
const HEALTH_URL = `http://127.0.0.1:${BACKEND_PORT}/api/health`;
const HEARTBEAT_INTERVAL = 500; // ms
const HEARTBEAT_TIMEOUT = 30000; // ms

/**
 * 健康响应的身份判定（纯函数，见 docs/decisions/port-identity.md）：200 且 JSON
 * `{"status":"ok"}` 才算「本工作台的后端在跑」——此前的「正文含 ok」子串匹配
 * 会连返回 ok 字样的陌生服务一起放行（复用 = 界面接上别的进程）。非 JSON /
 * 字段不对 → 未就绪。
 */
function isHealthy(statusCode, body) {
  if (statusCode !== 200) return false;
  try {
    const parsed = JSON.parse(body);
    return !!parsed && parsed.status === "ok";
  } catch {
    return false;
  }
}

function createBackendProcess({
  app, log, notifyUser, tFor, resolvedLang, backendDir,
  fs = require("fs"), path = require("path"), http = require("http"),
  childProcess = require("child_process"), env = process.env,
  platform = process.platform, resourcesPath = process.resourcesPath,
}) {
  let backendProcess = null;
  let backendReady = false;
  // 「主动停止」标志：stopBackend()（关窗 / 退出流程）置位；`exit` 回调据此把
  // 「我们自己杀的」与「后端自己崩的」分开。不加它的后果实测过（2026-09-25）：
  // 关窗时 taskkill 强杀 → 退出码非 0 → 被当成"运行中崩溃"弹窗——用户已经关窗，
  // 还弹出一个错误框。Electron 的退出事件只有 code 没有 signal，行业通行修法
  // 就是应用层标志位（见 `stopBackend` / `exit` 两处）。
  let backendStopping = false;

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
    return { ...env, JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: app.getVersion() };
  }

  // ---- Python 探测（优先级：JOBWS_PYTHON 环境变量 → PATH 中 python → python3）----
  function detectPython() {
    const candidates = [];
    if (env.JOBWS_PYTHON) {
      candidates.push(env.JOBWS_PYTHON);
    }
    // PATH 中的可执行文件（Windows 上 python.exe）
    const whichPython = findOnPath("python");
    if (whichPython) candidates.push(whichPython);
    const whichPython3 = findOnPath("python3");
    if (whichPython3) candidates.push(whichPython3);

    for (const cand of candidates) {
      try {
        // 验证能运行，且含 FastAPI/uvicorn
        const out = childProcess
          .execFileSync(cand, ["-c", "import uvicorn, fastapi; print('ok')"], {
            timeout: 10000,
            stdio: "pipe",
          })
          .toString()
          .trim();
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
    const sep = platform === "win32" ? ";" : ":";
    const paths = (env.PATH || "").split(sep);
    const exts = platform === "win32" ? [".exe", ".cmd", ""] : [""];
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
      res.on("end", () => once(isHealthy(res.statusCode, body)));
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
            `${t("backendTimeoutMessage", { seconds: HEARTBEAT_TIMEOUT / 1000 })}\n\n${HEALTH_URL}`,
            { withDiagnostics: true });
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
    const candidate = path.join(resourcesPath, "backend", "job-workbench-backend.exe");
    return fs.existsSync(candidate) ? candidate : null;
  }

  function startBackend() {
    if (backendProcess) return;
    backendStopping = false;   // 新一次启动：清掉上一轮「主动停止」标志

    const exe = findBackendExe();
    if (exe) {
      log(`Using packaged backend: ${exe}`);
      backendProcess = childProcess.spawn(exe, [], {
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
        notifyUser(t("backendMissingPythonTitle"), t("backendMissingPythonMessage"),
                   { withDiagnostics: true });
        app.quit();
        return;
      }
      log(`Using python backend: ${python}`);
      backendProcess = childProcess.spawn(python, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)], {
        cwd: backendDir,
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
      // 主动停止（关窗 / 退出流程走的 stopBackend）：正常路径，不弹窗——见
      // backendStopping 的注释（此前缺这个分支：关窗退出会误报"后端已停止"）。
      if (backendStopping) {
        log(`Backend stopped by app, code=${code}`);
        backendProcess = null;
        return;
      }
      // 2026-09-23 审计 P2：此前只写日志就静默自退（或窗口停在空白）——用户看到的
      // 是"双击了没反应"，而根因（后端起不来 / 中途崩了）只有打开日志才看得到。
      // 写日志与告诉用户是两件事，都要做。
      const t = tFor(resolvedLang());
      if (!backendReady && code !== 0) {
        log(`Backend exited unexpectedly, code=${code}`);
        notifyUser(t("backendStartFailedTitle"),
                   `${t("backendStartFailedMessage", { code })}\n\n${t("backendStartFailedDetail")}`,
                   { withDiagnostics: true });
      } else if (backendReady && code) {
        log(`Backend died while running, code=${code}`);
        notifyUser(t("backendDiedTitle"),
                   `${t("backendDiedMessage", { code })}\n\n${t("backendDiedDetail")}`,
                   { withDiagnostics: true });
      }
      backendProcess = null;
    });
  }

  function stopBackend() {
    if (!backendProcess) return;
    backendStopping = true;   // 先置位再杀：exit 回调是异步的，顺序反了会漏
    const pid = backendProcess.pid;
    try {
      if (platform === "win32") {
        // taskkill /t 杀进程树，避免 uvicorn/exe 的孙进程变成孤儿（调研确认的坑）
        childProcess.execSync(`taskkill /pid ${pid} /f /t`, { stdio: "ignore" });
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

  /** whenReady 复用已运行后端时调用（即 main.js 里 `backendReady = true` 的那处语义）。 */
  function markReady() {
    backendReady = true;
  }

  /** 读 backendReady（从不复位）。 */
  function isReady() {
    return backendReady;
  }

  /** 读 backendProcess 是否非空。 */
  function isRunning() {
    return backendProcess !== null;
  }

  return {
    BACKEND_PORT,
    HEALTH_URL,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_TIMEOUT,
    backendEnv,
    detectPython,
    findOnPath,
    checkHealth,
    isHealthy,
    waitBackendReady,
    findBackendExe,
    startBackend,
    stopBackend,
    markReady,
    isReady,
    isRunning,
  };
}

module.exports = { createBackendProcess };
