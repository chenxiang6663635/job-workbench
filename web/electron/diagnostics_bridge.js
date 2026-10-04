// 诊断出口与用户提示的桥接层（#204：从 main.js 原样搬出，行为零变更）。
//
// 为什么单独成文件：故障当下用户唯一会看的界面就是那个弹窗（后端起不来时窗口可能根本
// 还没创建），"复制诊断信息 + 打开日志文件夹"是本地优先 / 无遥测承诺下把有效信息交出去
// 的标准形态（调研：VS Code 的 `Developer: Open Logs Folder`、Slack 故障弹窗里的
// Download Logs、Obsidian 生态的「复制诊断报告」命令）。内容拼装在 diagnostics.js
// （纯函数、有单测），这里只做调度——弹窗、读文件、写剪贴板。
//
// 与 zoom.js / window_state.js 同款约定：不 require("electron")——app / BrowserWindow /
// dialog / clipboard / shell 与 tFor / resolvedLang / logFilePath 全部注入，
// ipcMain 由 registerIpc(ipcMain) 传入（fs 可注入，测试用假件替换）。

const { buildDiagnostics } = require("./diagnostics");

function createDiagnosticsBridge({
  app, log, tFor, resolvedLang, logFilePath, BrowserWindow, dialog, clipboard, shell, os,
  fs = require("fs"),
}) {
  /**
   * 给用户一条**看得见**的说明。
   *
   * 为什么单独成函数：窗口可能还没创建（后端没起来正是窗口创建不了的原因），
   * 那时没有父窗口可用——`showMessageBox` 不传父窗口同样能弹（旧版走 `showErrorBox`
   * 兜底，但它**不能带按钮**，而后端起不来恰恰最需要"把日志交出去"的出口，
   * 所以统一走 showMessageBox，「有窗挂窗、无窗直弹」）。
   *
   * `withDiagnostics`：附一个「复制诊断信息」按钮——调研惯例（Slack 故障弹窗里的
   * Download Logs、Obsidian 生态的「复制诊断报告」命令）：故障当下这个弹窗是用户
   * 唯一会看的界面，信息出口就该在这里。默认只有 OK。
   */
  function notifyUser(title, message, { withDiagnostics = false } = {}) {
    const buttons = withDiagnostics ? [tFor(resolvedLang())("copyDiag"), "OK"] : ["OK"];
    const opts = {
      type: "error", title, message, buttons,
      defaultId: buttons.length - 1, cancelId: buttons.length - 1,
    };
    try {
      const win = BrowserWindow.getAllWindows()[0];
      const shown = win ? dialog.showMessageBox(win, opts) : dialog.showMessageBox(opts);
      shown
        .then(({ response }) => {
          if (withDiagnostics && response === 0) copyDiagnostics();
        })
        .catch((e) => log(`notifyUser failed: ${e.message}`));
    } catch (e) {
      // 通知失败不该变成第二次崩溃：日志里留一句即可
      log(`notifyUser failed: ${e.message}`);
    }
  }

  /** 读日志尾部 N 行（单文件上限 1MB，整读即可）；读不到时给一句可读说明。 */
  function readLogTail(lines) {
    try {
      const all = fs.readFileSync(logFilePath(), "utf8").split(/\r?\n/);
      return all.slice(-lines).join("\n");
    } catch (e) {
      return `(cannot read log: ${e.message})`;
    }
  }

  /**
   * 「复制诊断信息」：版本 / 平台 / 日志尾部（含 [backend-err]）→ 剪贴板。
   * 只在用户点按钮时执行、只进剪贴板——本地优先 / 无遥测承诺下的标准形态
   * （调研：Obsidian 生态的 "Generate full report with debug info"、Servarr 的"贴 Gist"）。
   * 主目录路径在拼装时脱敏（`diagnostics.redactHome`），产物可安全贴进公开 issue。
   */
  function copyDiagnostics() {
    try {
      const text = buildDiagnostics({
        version: app.getVersion(),
        electron: process.versions.electron,
        node: process.versions.node,
        platform: process.platform,
        arch: process.arch,
        logPath: logFilePath(),
        tail: readLogTail(200),
        home: os.homedir(),
      });
      clipboard.writeText(text);
      const t = tFor(resolvedLang());
      dialog.showMessageBox({
        type: "info", title: t("copyDiag"), message: t("diagCopied"), buttons: ["OK"],
      });
    } catch (e) {
      log(`copyDiagnostics failed: ${e.message}`);
    }
  }

  /**
   * 设置页「关于」卡的「打开日志文件夹」：系统文件管理器打开 userData
   * （日志与数据同目录：%APPDATA%\job-workbench）。调研惯例：VS Code 的
   * `Developer: Open Logs Folder`、GitHub Desktop 的 `Help → Show Logs in Explorer`。
   * ipcMain 由调用方传入（`registerIpc(ipcMain)`）：本模块不 require("electron")，
   * 测试里同样传替身。缺参直接抛错——通道静默缺失（preload 的 invoke 永远 reject）
   * 比启动期报错难查得多。
   */
  function registerIpc(ipcMain) {
    if (!ipcMain) {
      throw new Error(
        "registerIpc(ipcMain) needs Electron's ipcMain: diagnostics_bridge.js never requires electron"
      );
    }
    ipcMain.handle("app:open-log-folder", () => shell.openPath(app.getPath("userData")));
  }

  return { notifyUser, copyDiagnostics, readLogTail, registerIpc };
}

module.exports = { createDiagnosticsBridge };
