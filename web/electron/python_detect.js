// Python 探测（源码形态的后端回退路径）。
//
// 从 backend_process.js 抽出（2026-10-28）：`backend_process.js` 越过 300 行水位，
// 而这两个函数是**自包含的纯探测逻辑**——只依赖注入进来的 env / platform / path /
// fs / childProcess，不碰进程生命周期。零行为变更，只搬家。
//
// 优先级：`JOBWS_PYTHON` 环境变量 → PATH 中的 python → PATH 中的 python3。
// 每个候选都要真跑一次 `import uvicorn, fastapi`，能 import 才算数——
// 只看文件存在会选中一个缺依赖的解释器，启动时才炸。

/**
 * @param {object} deps 注入的依赖（全部必需）
 * @param {object} deps.env          环境变量（读 JOBWS_PYTHON / PATH）
 * @param {string} deps.platform     process.platform（决定分隔符与扩展名）
 * @param {object} deps.path         path 模块
 * @param {object} deps.fs           fs 模块（只用 existsSync）
 * @param {object} deps.childProcess 需要 execFileSync
 * @param {function} deps.log        日志函数
 */
function createPythonDetector({ env, platform, path, fs, childProcess, log }) {
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

  function detectPython() {
    const candidates = [];
    if (env.JOBWS_PYTHON) {
      candidates.push(env.JOBWS_PYTHON);
    }
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

  return { detectPython, findOnPath };
}

module.exports = { createPythonDetector };
