// 自动更新（electron-updater）的接线层（#204 拆分 D）。
// 只在打包形态启用：源码运行时没有 app-update.yml，检查必然失败，开发者也不需要它。
//
// 交互刻意做成"两次询问"：先问要不要下载，下载完再问要不要重启。
// 静默下载 + 静默重启是更省事的写法，但会打断用户正在做的事——而这个应用一关窗口
// 后端进程也停，重启的代价比一般桌面应用更高，必须由用户自己挑时机。
//
// 不 require("electron")：app / dialog 全部注入；electron-updater 保持**函数内动态
// require**（依赖没打进包时，本模块也要能安全加载）。
function createUpdater({ app, log, tFor, resolvedLang, dialog, stopBackend, notifyUser, timers = { setTimeout } }) {
  function setup() {
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
    // 错误分级（发布前审计 发现 3）：检查阶段的失败（离线 / GitHub API 限流——
    // 未认证请求 60 次/小时/IP）只进日志；此时用户还没介入，弹模态既吓人又可能
    // 每次启动都弹一次。用户点了「下载更新」之后才切换到弹窗——他正在等结果，
    // 那时静默才是不可接受的。
    let updateDownloadRequested = false;

    autoUpdater.on("error", (err) => {
      const reason = (err && err.message) || String(err);
      log(`Auto-update error: ${reason}`);
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
    timers.setTimeout(() => {
      autoUpdater.checkForUpdates().catch((e) => log(`Update check failed: ${e.message}`));
    }, 5000);
  }

  return { setup };
}

module.exports = { createUpdater };
