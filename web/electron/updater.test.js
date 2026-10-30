// 自动更新的接线层（`updater.js`）——此前**零测试**（2026-10-30 补）。
//
// 为什么现在补：真机实测发现两个问题
//   1. 差分下载虽然把 131 MB 压到 6.4 MB，但国内 GitHub 资产只有 ~84 KB/s，
//      那一次下载用了 **76 秒，全程没有任何反馈**——用户以为卡住了。
//   2. 首次 `checkForUpdates` 遇到 `net::ERR_TIMED_OUT`，关掉重开才成功。
//
// 这两个都不是「设计问题」，是**没有被测到的行为**。这里钉住修复。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode 会拦中文串）。
const test = require("node:test");
const assert = require("node:assert/strict");

const { createUpdater } = require("./updater");

/** 假 autoUpdater：记录 on() 注册的处理器，测试手动触发。 */
function fakeAutoUpdater({ rejectCheck = false } = {}) {
  const handlers = {};
  const state = { checks: 0, downloads: 0, installed: 0 };
  return {
    state,
    handlers,
    autoDownload: null,
    logger: null,
    on: (e, fn) => {
      (handlers[e] = handlers[e] || []).push(fn);
    },
    checkForUpdates: () => {
      state.checks += 1;
      return rejectCheck ? Promise.reject(new Error("net::ERR_TIMED_OUT")) : Promise.resolve();
    },
    downloadUpdate: () => {
      state.downloads += 1;
      return Promise.resolve();
    },
    quitAndInstall: () => {
      state.installed += 1;
    },
    fire: (e, arg) => (handlers[e] || []).forEach((fn) => fn(arg)),
  };
}

/** 假 BrowserWindow：只关心 setProgressBar。 */
function fakeWindow() {
  const progress = [];
  return {
    progress,
    setProgressBar: (v) => progress.push(v),
  };
}

/** 同步 timers：`setTimeout(fn)` 直接执行（重试次数由 checkAttempts 限住）。 */
const syncTimers = { setTimeout: (fn) => { fn(); return 0; } };

function makeUpdater({ rejectCheck = false, win = fakeWindow(), dialog = null } = {}) {
  const logs = [];
  const updater = fakeAutoUpdater({ rejectCheck });
  const bridge = createUpdater({
    app: { isPackaged: true, getVersion: () => "26.11.0" },
    log: (m) => logs.push(m),
    tFor: () => (k) => k,
    resolvedLang: () => "en",
    dialog: dialog || { showMessageBox: () => Promise.resolve({ response: 1 }) },
    stopBackend: () => {},
    notifyUser: () => Promise.resolve(),
    BrowserWindow: win ? { getAllWindows: () => [win] } : null,
    autoUpdater: updater,
    timers: syncTimers,
  });
  bridge.setup();
  return { bridge, updater, logs, win };
}

test("download-progress drives the taskbar progress bar", () => {
  const { updater, win } = makeUpdater();
  updater.fire("download-progress", { percent: 42.4, transferred: 1048576, total: 2097152 });
  assert.deepEqual(win.progress, [0.42],
    "progress must reach the taskbar — 76s of silence is what made it feel stuck");
});

test("download-progress logs the percentage and size", () => {
  const { updater, logs } = makeUpdater();
  updater.fire("download-progress", { percent: 50, transferred: 3145728, total: 6291456 });
  assert.ok(logs.some((l) => l.includes("Update download 50%") && l.includes("3.0")),
    `expected a progress log line, got: ${logs.join(" | ")}`);
});

test("update-downloaded clears the progress bar", () => {
  const { updater, win } = makeUpdater();
  updater.fire("download-progress", { percent: 100, transferred: 1, total: 1 });
  updater.fire("update-downloaded", { version: "26.11.0" });
  assert.equal(win.progress.at(-1), -1, "-1 clears it; otherwise it stays frozen at full");
});

test("a download error clears the progress bar too", () => {
  const { updater, win } = makeUpdater();
  updater.fire("download-progress", { percent: 30, transferred: 1, total: 1 });
  updater.fire("error", new Error("boom"));
  assert.equal(win.progress.at(-1), -1,
    "a failed download must not leave the taskbar stuck mid-way");
});

test("a failing update check retries exactly once", async () => {
  // 2026-10-30 实测：首次检查 net::ERR_TIMED_OUT，关掉重开才成功。
  const { updater, logs } = makeUpdater({ rejectCheck: true });
  // `checkForUpdates` 返回 rejected promise，`.catch` 在 microtask 里跑；
  // 而 timers 是同步假的，所以要等一轮事件循环再断言，否则看到的是「还没重试」。
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(updater.state.checks, 2, "one retry — not infinite, not zero");
  assert.ok(logs.some((l) => l.includes("attempt 1")) && logs.some((l) => l.includes("attempt 2")),
    `both attempts should be logged, got: ${logs.join(" | ")}`);
});

test("a successful update check does not retry", () => {
  const { updater } = makeUpdater({ rejectCheck: false });
  assert.equal(updater.state.checks, 1, "success must not trigger a second check");
});

test("source runs skip auto-update entirely", () => {
  const logs = [];
  const updater = fakeAutoUpdater();
  createUpdater({
    app: { isPackaged: false, getVersion: () => "26.11.0" },
    log: (m) => logs.push(m),
    tFor: () => (k) => k,
    resolvedLang: () => "en",
    dialog: { showMessageBox: () => Promise.resolve({ response: 1 }) },
    stopBackend: () => {},
    notifyUser: () => Promise.resolve(),
    BrowserWindow: null,
    autoUpdater: updater,
    timers: syncTimers,
  }).setup();
  assert.equal(updater.state.checks, 0, "dev runs have no app-update.yml");
  assert.ok(logs.some((l) => l.includes("Source run")));
});

test("no window means no progress bar, but the download still works", () => {
  const { updater } = makeUpdater({ win: null });
  updater.fire("download-progress", { percent: 10, transferred: 1, total: 10 });
  updater.fire("update-downloaded", { version: "26.11.0" });
  // 只是不能崩——后端起不来时窗口可能还没建
  assert.equal(updater.state.checks, 1);
});
