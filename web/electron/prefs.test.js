// 偏好通道（界面缩放 + 界面语言）的单测：`node web/electron/prefs.test.js`（CI 也跑这一步）。
// prefs.js 不 require("electron")：app / BrowserWindow / tFor / ipcMain / fs 全部用替身注入，
// 于是"落盘与广播的时机、同值幂等、夹取边界、快捷键的命中与不命中"都能在这一层钉住。
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { ZOOM_MIN, ZOOM_MAX, ZOOM_STEP } = require("./zoom");
const { createPrefs } = require("./prefs");

const USER_DATA = "userData";
const ZOOM_PATH = path.join(USER_DATA, "zoom.json");

/** 假窗口：记录 setZoomLevel / send / setTitle，并暴露事件触发口。 */
function makeWindow() {
  const listeners = {};
  const win = { titleSets: [], zoomLevels: [], sends: [], setTitle(value) { win.titleSets.push(value); } };
  win.webContents = {
    setZoomLevel(value) { win.zoomLevels.push(value); },
    send(channel, payload) { win.sends.push({ channel, payload }); },
    on(name, fn) { listeners[name] = fn; },
  };
  win.emit = (name, ...args) => listeners[name](...args);
  return win;
}

/** 假 ipcMain：按 Electron 的 (event, ...args) 形状派发到已注册的 handler。 */
function makeIpcMain() {
  const handlers = new Map();
  return {
    handle(channel, fn) { handlers.set(channel, fn); },
    channels() { return [...handlers.keys()]; },
    invoke(channel, ...args) {
      assert.ok(handlers.has(channel), `no handler registered for ${channel}`);
      return handlers.get(channel)(null, ...args);
    },
  };
}

function withIpc(env) {   // 注册 IPC 后返回假 ipcMain
  const ipcMain = makeIpcMain();
  env.prefs.registerIpc(ipcMain);
  return ipcMain;
}

/** 假键盘事件：只关心 preventDefault 是否被调用。 */
function makeKeyEvent() {
  return { prevented: false, preventDefault() { this.prevented = true; } };
}

/** before-input-event 的 input：默认 keyDown、无修饰键，按需覆盖。 */
function keyInput(key, overrides = {}) {
  return { type: "keyDown", key, control: false, meta: false, alt: false, ...overrides };
}

/** 组装一套带内存 fs 的替身环境；store 便于直接查看"磁盘"内容。 */
function makeEnv({ files = {}, locale = "en", platform = "win32" } = {}) {
  const store = new Map(Object.entries(files));
  const fsCalls = { reads: [], writes: [], mkdirs: [] };
  const fs = {
    readFileSync(file) {
      fsCalls.reads.push(file);
      if (!store.has(file)) throw new Error(`ENOENT: no such file: ${file}`);
      return store.get(file);
    },
    writeFileSync(file, data) { fsCalls.writes.push(file); store.set(file, data); },
    mkdirSync(dir) { fsCalls.mkdirs.push(dir); },
  };
  const logs = [];
  const windows = [];
  const app = { getPath: () => USER_DATA, getLocale: () => locale };
  const tFor = (lang) => (key) => `${lang}:${key}`;
  const BrowserWindow = { getAllWindows: () => windows };
  const prefs = createPrefs({
    app, log: (line) => logs.push(line), BrowserWindow, tFor, fs, path, platform,
  });
  return { prefs, windows, logs, fsCalls, store, fs };
}
// --- 加载与快照 -----------------------------------------------------------------

test("loadFromDisk reads the persisted level", () => {
  const env = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: 2.5 }) } });
  env.prefs.loadFromDisk();
  assert.equal(env.prefs.getZoomLevel(), 2.5);
});

test("loadFromDisk falls back to 0 when zoom.json is missing or unusable", () => {
  const missing = makeEnv();
  missing.prefs.loadFromDisk();
  assert.equal(missing.prefs.getZoomLevel(), 0, "no file yet");
  const corrupt = makeEnv({ files: { [ZOOM_PATH]: "{ not json" } });
  corrupt.prefs.loadFromDisk();
  assert.equal(corrupt.prefs.getZoomLevel(), 0, "a corrupt file must not break startup");
  const garbage = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: "big" }) } });
  garbage.prefs.loadFromDisk();
  assert.equal(garbage.prefs.getZoomLevel(), 0, "a non-numeric level means the default");
});

test("snapshot exposes the full UI contract", () => {
  const env = makeEnv({ locale: "zh-CN" });
  assert.deepEqual(
    env.prefs.snapshot(),
    { level: 0, min: ZOOM_MIN, max: ZOOM_MAX, step: ZOOM_STEP, percent: 100, lang: "zh-CN" }
  );
});

test("resolvedLang falls back to the system locale before any report", () => {
  const env = makeEnv({ locale: "zh-CN" });
  assert.equal(env.prefs.resolvedLang(), "zh-CN");
});

// --- 缩放写入口：落盘 / 广播 / 幂等 / 夹取 ---------------------------------------

test("applyZoomChange persists and broadcasts by default", () => {
  const env = makeEnv();
  const win = makeWindow();
  env.windows.push(win);
  assert.deepEqual(env.prefs.applyZoomChange(1, true), { level: 1, percent: 120 });
  assert.deepEqual(win.zoomLevels, [1], "the new level is applied to every window");
  assert.deepEqual(env.fsCalls.writes, [ZOOM_PATH]);
  assert.equal(env.store.get(ZOOM_PATH), JSON.stringify({ level: 1 }, null, 2));
  assert.deepEqual(win.sends, [
    { channel: "prefs:zoom-changed", payload: { level: 1, percent: 120 } },
  ]);
});

test("a preview (persist=false) applies the level but does not write or broadcast", () => {
  const env = makeEnv();
  const win = makeWindow();
  env.windows.push(win);
  assert.deepEqual(env.prefs.applyZoomChange(2, false), { level: 2, percent: 144 });
  assert.deepEqual(win.zoomLevels, [2]);
  assert.equal(env.fsCalls.writes.length, 0, "a preview must not hit the disk");
  assert.equal(win.sends.length, 0, "a preview must not broadcast");
});

test("asking for the current level is a no-op (no write, no broadcast, no re-apply)", () => {
  const env = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: 1 }) } });
  const win = makeWindow();
  env.windows.push(win);
  env.prefs.loadFromDisk();
  assert.deepEqual(env.prefs.applyZoomChange(1, true), { level: 1, percent: 120 });
  assert.equal(env.fsCalls.writes.length, 0);
  assert.equal(win.sends.length, 0);
  assert.equal(win.zoomLevels.length, 0, "no window touched for an unchanged level");
});

test("applyZoomChange clamps through the zoom.js bounds", () => {
  const env = makeEnv();
  assert.deepEqual(env.prefs.applyZoomChange(99, false), { level: ZOOM_MAX, percent: 173 });
  assert.deepEqual(env.prefs.applyZoomChange(-99, false), { level: ZOOM_MIN, percent: 58 });
  assert.deepEqual(env.prefs.applyZoomChange(Number.NaN, false), { level: 0, percent: 100 });
});

test("applyZoomToWindow only sets the level on that window", () => {
  const env = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: 2 }) } });
  env.prefs.loadFromDisk();
  const win = makeWindow();
  env.prefs.applyZoomToWindow(win);
  assert.deepEqual(win.zoomLevels, [2]);
  assert.equal(win.sends.length, 0, "applying to one window must not broadcast");
});

test("a failed disk write only logs and keeps the applied level", () => {
  const env = makeEnv();
  env.fs.writeFileSync = () => { throw new Error("disk full"); };
  const win = makeWindow();
  env.windows.push(win);
  assert.deepEqual(env.prefs.applyZoomChange(1, true), { level: 1, percent: 120 });
  assert.ok(env.logs.some((line) => line.includes("Failed to persist zoom level")), "the failure is logged");
  assert.equal(win.sends.length, 1, "a failed write still broadcasts the applied value");
});

// --- IPC：prefs:set-zoom / prefs:set-lang ----------------------------------------

test("registerIpc registers exactly the two preference channels", () => {
  const env = makeEnv();
  assert.deepEqual(withIpc(env).channels(), ["prefs:set-zoom", "prefs:set-lang"]);
});

test("prefs:set-zoom persists by default (persist omitted)", () => {
  const env = makeEnv();
  const ipcMain = withIpc(env);
  assert.deepEqual(ipcMain.invoke("prefs:set-zoom", { level: 1.5 }), { level: 1.5, percent: 131 });
  assert.equal(env.fsCalls.writes.length, 1, "an omitted persist flag must still write");
});

test("prefs:set-zoom honors persist=false for slider previews", () => {
  const env = makeEnv();
  const ipcMain = withIpc(env);
  assert.deepEqual(ipcMain.invoke("prefs:set-zoom", { level: 1.5, persist: false }), { level: 1.5, percent: 131 });
  assert.equal(env.fsCalls.writes.length, 0);
});

test("prefs:set-lang accepts a supported report and retitles windows", () => {
  const env = makeEnv({ locale: "en" });
  const win = makeWindow();
  env.windows.push(win);
  const ipcMain = withIpc(env);
  assert.deepEqual(ipcMain.invoke("prefs:set-lang", "zh-CN"), { lang: "zh-CN" });
  assert.equal(env.prefs.resolvedLang(), "zh-CN");
  assert.deepEqual(win.titleSets, ["zh-CN:windowTitle"]);
  assert.ok(env.logs.some((line) => line.includes("UI language reported by renderer: zh-CN")));
});

test("prefs:set-lang ignores an unsupported language and logs it", () => {
  const env = makeEnv({ locale: "en" });
  const ipcMain = withIpc(env);
  assert.deepEqual(ipcMain.invoke("prefs:set-lang", "fr"), { lang: "en" });
  assert.equal(env.prefs.resolvedLang(), "en", "an untrusted report must not enter state");
  assert.ok(env.logs.some((line) => line.includes("Ignored unknown UI language report: fr")));
});

test("prefs:set-lang treats empty reports as unsupported", () => {
  const env = makeEnv({ locale: "en" });
  assert.deepEqual(withIpc(env).invoke("prefs:set-lang", null), { lang: "en" });
});

test("prefs:set-lang is a no-op when the language does not change", () => {
  const env = makeEnv({ locale: "en" });
  const win = makeWindow();
  env.windows.push(win);
  const ipcMain = withIpc(env);
  ipcMain.invoke("prefs:set-lang", "zh-CN");
  assert.deepEqual(ipcMain.invoke("prefs:set-lang", "zh-CN"), { lang: "zh-CN" });
  assert.equal(win.titleSets.length, 1, "the title is set only on an actual change");
});

// --- 快捷键（before-input-event） ------------------------------------------------

test("Ctrl+= zooms in one step, persists, and blocks the default menu", () => {
  const env = makeEnv();
  const win = makeWindow();
  env.windows.push(win);
  env.prefs.attachZoomShortcuts(win);
  const event = makeKeyEvent();
  win.emit("before-input-event", event, keyInput("=", { control: true }));
  assert.equal(event.prevented, true, "the default menu must be blocked");
  assert.equal(env.prefs.getZoomLevel(), 0.5);
  assert.equal(env.fsCalls.writes.length, 1, "shortcut changes persist");
  assert.equal(win.sends.length, 1, "shortcut changes broadcast");
  assert.ok(env.logs.includes("Zoom level: 0.5"));
});

test("keys without a zoom modifier or on key-up pass through untouched", () => {
  const env = makeEnv();
  const win = makeWindow();
  env.prefs.attachZoomShortcuts(win);
  const plain = makeKeyEvent();
  win.emit("before-input-event", plain, keyInput("="));
  const withAlt = makeKeyEvent();
  win.emit("before-input-event", withAlt, keyInput("=", { control: true, alt: true }));
  const keyUp = makeKeyEvent();
  win.emit("before-input-event", keyUp, keyInput("=", { control: true, type: "keyUp" }));
  assert.equal(plain.prevented, false);
  assert.equal(withAlt.prevented, false);
  assert.equal(keyUp.prevented, false);
  assert.equal(env.prefs.getZoomLevel(), 0);
});

test("Ctrl+0 resets to 100%", () => {
  const env = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: 2 }) } });
  env.prefs.loadFromDisk();
  const win = makeWindow();
  env.prefs.attachZoomShortcuts(win);
  const event = makeKeyEvent();
  win.emit("before-input-event", event, keyInput("0", { control: true }));
  assert.equal(event.prevented, true);
  assert.equal(env.prefs.getZoomLevel(), 0);
});

test("a key at the zoom limit is swallowed but changes nothing", () => {
  const env = makeEnv({ files: { [ZOOM_PATH]: JSON.stringify({ level: 3 }) } });
  const win = makeWindow();
  env.windows.push(win);
  env.prefs.loadFromDisk();
  env.prefs.attachZoomShortcuts(win);
  const event = makeKeyEvent();
  win.emit("before-input-event", event, keyInput("=", { control: true }));
  assert.equal(event.prevented, true, "still blocked so the default menu cannot double-zoom");
  assert.equal(env.prefs.getZoomLevel(), 3);
  assert.equal(env.fsCalls.writes.length, 0);
  assert.equal(win.sends.length, 0);
});

test("on darwin the Cmd modifier drives zoom (Ctrl does not)", () => {
  const env = makeEnv({ platform: "darwin" });
  const win = makeWindow();
  env.prefs.attachZoomShortcuts(win);
  const ctrlEvent = makeKeyEvent();
  win.emit("before-input-event", ctrlEvent, keyInput("=", { control: true }));
  assert.equal(ctrlEvent.prevented, false, "Ctrl is not the modifier on darwin");
  const metaEvent = makeKeyEvent();
  win.emit("before-input-event", metaEvent, keyInput("=", { meta: true }));
  assert.equal(metaEvent.prevented, true);
  assert.equal(env.prefs.getZoomLevel(), 0.5);
});
