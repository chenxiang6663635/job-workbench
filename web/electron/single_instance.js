// AUMID 与单实例锁（发布前审计 发现 1 / 发现 4）——#204 拆分 D。
// 契约：调用本函数的当下**同步**完成四件事：setAppUserModelId、
// requestSingleInstanceLock、second-instance 注册、无锁时 app.quit()——
// 与 main.js 原流程（模块加载期执行）等价；返回 hasLock 供启动链路决定后续。
//
// 不 require("electron")：app / BrowserWindow 注入。

function createSingleInstance({ app, BrowserWindow, log }) {
  // AUMID：Windows 通知要求进程的 AppUserModelID 与开始菜单快捷方式一致；只有
  // Squirrel 打包会自动调 setAppUserModelId，electron-builder（NSIS）不会——不设的
  // 话安装版上「到点提醒」的 toast 会被系统静默丢弃：不报错、不崩溃，就是收不到
  // （CI 冒烟测不出通知）。取值必须与 package.json 的 build.appId 一致。
  app.setAppUserModelId("com.jobworkbench.app");

  // 单实例锁：双开是首发期最常见的操作（「双击没反应就再双击一下」）。没有锁时
  // 第二实例直接复用第一实例的后端，而「关窗即停」挂在每个窗口上——关掉先启动的
  // 那个窗口，共享的后端被杀，另一窗口界面还在而全部请求失效。加锁后第二实例直接
  // 退出，已有窗口被拉到前面（second-instance）。
  const hasLock = app.requestSingleInstanceLock();
  if (!hasLock) {
    app.quit();
  }
  // 照搬 main.js 的同步流程：无论是否拿到锁都注册 second-instance（无锁实例随即退出，
  // 注册本身无副作用，与既有行为保持一致）。
  app.on("second-instance", () => {
    const win = BrowserWindow.getAllWindows()[0];
    if (win) {
      if (win.isMinimized()) win.restore();
      win.show();
      win.focus();
    }
  });

  return { hasLock };
}

module.exports = { createSingleInstance };
