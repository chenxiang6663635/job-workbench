// 自动更新（electron-updater）的接线层（#204 拆分 D）。
// 只在打包形态启用：源码运行时没有 app-update.yml，检查必然失败，开发者也不需要它。
//
// 交互刻意做成"两次询问"：先问要不要下载，下载完再问要不要重启。
// 静默下载 + 静默重启是更省事的写法，但会打断用户正在做的事——而这个应用一关窗口
// 后端进程也停，重启的代价比一般桌面应用更高，必须由用户自己挑时机。
//
// 不 require("electron")：app / dialog 全部注入；electron-updater 保持**函数内动态
// require**（依赖没打进包时，本模块也要能安全加载）。
function createUpdater({
  app, log, tFor, resolvedLang, dialog, stopBackend, notifyUser,
  BrowserWindow = null,   // 用于任务栏进度条（2026-10-30）；测试可传 null
  autoUpdater: injectedUpdater = null,   // 测试注入假件；生产走下面的动态 require
  timers = { setTimeout },
}) {
  function setup() {
    if (!app.isPackaged) {
      log("Source run — skipping auto-update check");
      return;
    }

    let autoUpdater = injectedUpdater;
    if (!autoUpdater) {
      try {
        ({ autoUpdater } = require("electron-updater"));
      } catch (e) {
        // 依赖没打进包时不该让整个应用起不来——更新只是增强，不是启动必需
        log(`Auto-update unavailable (electron-updater not bundled): ${e.message}`);
        return;
      }
    }

    autoUpdater.autoDownload = false;
    // 用主进程日志接手 updater 的输出：GUI 下看不到控制台，出问题只能靠这个文件
    autoUpdater.logger = { info: log, warn: log, error: log, debug: () => {} };

    /**
     * 任务栏进度条（`-1` 清除）。窗口可能还没建（后端起不来时），静默跳过。
     *
     * 为什么选任务栏而不是弹窗（2026-10-30 实测）：差分已经生效（131 MB → 6.4 MB），
     * 但 GitHub 资产在国内只有 ~84 KB/s——那次下载用了 76 秒，而**全程没有任何反馈**，
     * 用户点完「下载」看到的是一个不动的窗口，自然觉得「卡住了」。
     * `setProgressBar` 是 Electron 原生能力，零 UI 组件、一眼可见。
     */
    function setTaskbarProgress(value) {
      try {
        const win = BrowserWindow && BrowserWindow.getAllWindows()[0];
        if (win && typeof win.setProgressBar === "function") win.setProgressBar(value);
      } catch (e) {
        log(`setProgressBar failed: ${e.message}`);   // 进度显示失败不该拖累更新本身
      }
    }

    autoUpdater.on("download-progress", (p) => {
      const pct = Math.max(0, Math.min(100, Math.round(p.percent || 0)));
      log(`Update download ${pct}% (${(p.transferred / 1048576).toFixed(1)}`
        + ` / ${(p.total / 1048576).toFixed(1)} MB)`);
      setTaskbarProgress(pct / 100);
    });
    // 错误分级（发布前审计 发现 3）：检查阶段的失败（离线 / GitHub API 限流——
    // 未认证请求 60 次/小时/IP）只进日志；此时用户还没介入，弹模态既吓人又可能
    // 每次启动都弹一次。用户点了「下载更新」之后才切换到弹窗——他正在等结果，
    // 那时静默才是不可接受的。
    let updateDownloadRequested = false;

    autoUpdater.on("error", (err) => {
      const reason = (err && err.message) || String(err);
      log(`Auto-update error: ${reason}`);
      setTaskbarProgress(-1);   // 失败也要清掉，否则任务栏会永远停在中间
      if (!updateDownloadRequested) return;
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
          updateDownloadRequested = true; // 从这里起，更新流程的失败要告知用户
          autoUpdater.downloadUpdate().catch((e) => log(`Update download failed: ${e.message}`));
        });
    });

    autoUpdater.on("update-downloaded", (info) => {
      log(`Update downloaded: ${info.version}`);
      setTaskbarProgress(-1);   // 下载完成即清进度条，剩下的交给「重启」那个弹窗
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

    // 延迟检查：让窗口先渲染出来，别和启动链路抢时间。
    //
    // **失败重试一次**（2026-10-30 实测）：首次检查遇到 `net::ERR_TIMED_OUT`，
    // 关掉重开才成功——国内访问 GitHub API 抖动是常态，一次重试能覆盖大部分情况。
    // 只重试**失败**（reject）；`update-not-available` 是正常结果，不重试。
    let checkAttempts = 0;
    const checkOnce = () => {
      checkAttempts += 1;
      autoUpdater.checkForUpdates().catch((e) => {
        log(`Update check failed (attempt ${checkAttempts}): ${e.message}`);
        if (checkAttempts < 2) timers.setTimeout(checkOnce, 30000);
      });
    };
    timers.setTimeout(checkOnce, 5000);
  }

  return { setup };
}

module.exports = { createUpdater };
