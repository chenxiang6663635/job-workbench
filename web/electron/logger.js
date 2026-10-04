// 求职工作台 · 主进程日志（从 main.js 原样搬出，行为零变更）。
//
// 为什么是工厂而不是模块级函数：日志要落盘到 userData，落点的唯一来源是
// app.getPath——原实现里 app 是模块级依赖；拆出后经 deps 注入，本文件不
// require("electron")，也就能被 node 直接跑（行为仍由 main.js 的调用点决定）。
//
// 搬运时必须保持的不变量（改动前先回 main.js 对照）：
//   - 日志行前缀 `[job-workbench] <ISO 时间戳> `，逐字保持；
//   - 文件超过 1MB 轮转为 .old，避免无限增长；
//   - 全程 try/catch 不抛——日志失败不影响主流程；
//   - 面向用户的字符串与日志一律英文（i18n 硬编码检查会拦中文串）。

function createLogger({ app, fs = require("fs"), path = require("path") }) {
  // 日志文件路径（log() 与「复制诊断信息」共用；userData = %APPDATA%\job-workbench）。
  // 惰性求值而不是模块级常量：userData 的解析尽量贴近既有行为（原来就在 log() 内取）。
  function logFilePath() {
    return path.join(app.getPath("userData"), "main.log");
  }

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
      const lp = logFilePath();
      if (fs.existsSync(lp) && fs.statSync(lp).size > 1024 * 1024) {
        fs.renameSync(lp, `${lp}.old`);
      }
      fs.appendFileSync(lp, `${line}\n`);
    } catch (e) {
      // 日志失败不影响主流程
    }
  }

  return { log, logFilePath };
}

module.exports = { createLogger };
