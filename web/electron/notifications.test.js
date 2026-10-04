// notifications.js 的可判定行为单测：`node web/electron/notifications.test.js`。
// 覆盖搬运（#204 从 main.js 拆出）中容易回归的硬约定：坏文件回落、days 夹取、
// 布尔/对象两种 set-reminders 形态、workspace trim、timer 幂等、enabled=false 不发
// 请求、点通知发 reminder:focus。
//
// 断言消息用英文（electron 树的字符串口径是英文，check_i18n_hardcode.py 会拦中文串）；
// 注释按仓库惯例用中文。依赖注入全部换假件：内存 fs / 假 http / 假 Notification /
// 假 BrowserWindow——不 require("electron")，也不需要后端。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");

const { createNotifications } = require("./notifications");
const { todayKey } = require("./reminders");

const USER_DATA = "/fake-userdata";
const BACKEND_PORT = 8765;

// ---- 假件 ----------------------------------------------------------------------

/** 内存 fs：预置内容、记录写入；读缺失文件照常抛错（模块内按默认回落）。 */
function makeMemoryFs(files) {
  const store = { ...files };
  return {
    store,
    readFileSync(file) {
      if (!(file in store)) throw new Error(`ENOENT: no such file, open '${file}'`);
      return store[file];
    },
    writeFileSync(file, data) { store[file] = String(data); },
    mkdirSync() {},
  };
}

function makeFakeRes() {
  const handlers = {};
  return {
    statusCode: 200,
    on(event, fn) { handlers[event] = fn; },
    emit(event, arg) { if (handlers[event]) handlers[event](arg); },
  };
}

/** 驱动一次假的 /api/reminders/due 响应。 */
function answer(call, { statusCode = 200, body } = {}) {
  const res = makeFakeRes();
  call.callback(res);
  res.statusCode = statusCode;
  if (body !== undefined) res.emit("data", body);
  res.emit("end");
}

function dueBody(todos) {
  return JSON.stringify({ counts: { todos: todos.length, talks: 0, overdue: 0 }, todos });
}

function makeHarness({ fileContent, intervalMs = 1000 } = {}) {
  const remindersFile = path.join(USER_DATA, "reminders.json");
  const fs = makeMemoryFs(fileContent === undefined ? {} : { [remindersFile]: fileContent });
  const httpCalls = [];
  const http = {
    get(url, options, callback) {
      const handlers = {};
      const req = {
        handlers,
        on(event, fn) { handlers[event] = fn; return this; },
        destroy() { handlers.destroyed = true; },
      };
      httpCalls.push({ url, options, callback, req });
      return req;
    },
  };
  const timers = {
    setCount: 0, clearCount: 0, lastMs: null,
    setInterval(fn, ms) { timers.setCount += 1; timers.lastMs = ms; return `timer-${timers.setCount}`; },
    clearInterval() { timers.clearCount += 1; },
  };
  const notifications = [];
  class FakeNotification {
    constructor(opts) { this.opts = opts; this.handlers = {}; this.shown = false; notifications.push(this); }
    on(event, fn) { this.handlers[event] = fn; }
    show() { this.shown = true; }
  }
  const windows = [];
  const logs = [];
  const ipcHandlers = new Map();
  const ipcMain = { handle: (channel, fn) => ipcHandlers.set(channel, fn) };
  const io = createNotifications({
    app: { getPath: () => USER_DATA },
    log: (msg) => logs.push(msg),
    tFor: () => (key) => key,
    resolvedLang: () => "en",
    BrowserWindow: { getAllWindows: () => windows },
    Notification: FakeNotification,
    backendPort: BACKEND_PORT,
    http,
    fs,
    path,
    timers,
    intervalMs,
  });
  return { io, ipcMain, fs, remindersFile, httpCalls, timers, notifications, windows, logs, ipcHandlers };
}

// ---- 状态装载：坏文件 / 缺失 / days 夹取 / 旧字段 ---------------------------------

test("loadState: corrupt or missing files fall back to defaults", () => {
  const corrupt = makeHarness({ fileContent: "{ not json" });
  corrupt.io.loadState();
  assert.deepStrictEqual(corrupt.io.reminderPrefs(), { enabled: true, days: 3 });

  const missing = makeHarness();
  missing.io.loadState();
  assert.deepStrictEqual(missing.io.reminderPrefs(), { enabled: true, days: 3 });

  const legacy = makeHarness({ fileContent: '{"enabled": false, "days": 5, "lastNotified": "2020-01-01"}' });
  legacy.io.loadState();
  assert.deepStrictEqual(legacy.io.reminderPrefs(), { enabled: false, days: 5 }, "enabled=false is kept");
});

test("loadState: days is clamped to 1..30; non-finite falls back to 3", () => {
  const daysOf = (fileContent) => {
    const h = makeHarness({ fileContent });
    h.io.loadState();
    return h.io.reminderPrefs().days;
  };
  assert.strictEqual(daysOf('{"days": 99}'), 30, "99 clamps down to 30");
  assert.strictEqual(daysOf('{"days": 0}'), 1, "0 clamps up to 1");
  assert.strictEqual(daysOf('{"days": "soon"}'), 3, "a non-finite value falls back to the default");
});

// ---- prefs:set-reminders：布尔 / 对象两种调用形态 ---------------------------------

test("registerIpc needs the injected ipcMain", () => {
  const h = makeHarness();
  assert.throws(() => h.io.registerIpc(), /ipcMain/);
});

test("prefs:set-reminders accepts a bare boolean (legacy call sites)", () => {
  const h = makeHarness();
  h.io.registerIpc(h.ipcMain);
  const setReminders = h.ipcHandlers.get("prefs:set-reminders");
  assert.deepStrictEqual(setReminders(null, false), { reminders: false, reminderDays: 3 });
  assert.deepStrictEqual(setReminders(null, true), { reminders: true, reminderDays: 3 });
});

test("prefs:set-reminders accepts {enabled, days}: clamps/rounds days, keeps the other field", () => {
  const h = makeHarness();
  h.io.registerIpc(h.ipcMain);
  const setReminders = h.ipcHandlers.get("prefs:set-reminders");
  assert.deepStrictEqual(setReminders(null, { days: 99 }), { reminders: true, reminderDays: 30 });
  assert.deepStrictEqual(setReminders(null, { days: 0 }), { reminders: true, reminderDays: 1 });
  assert.deepStrictEqual(setReminders(null, { days: 4.6 }), { reminders: true, reminderDays: 5 });
  assert.deepStrictEqual(setReminders(null, { enabled: false }), { reminders: false, reminderDays: 5 });
  assert.deepStrictEqual(setReminders(null, { days: "soon" }), { reminders: false, reminderDays: 5 });
});

test("prefs:set-reminders persists and checks right away only when enabled", () => {
  const h = makeHarness();
  h.io.registerIpc(h.ipcMain);
  const setReminders = h.ipcHandlers.get("prefs:set-reminders");
  setReminders(null, { days: 7 });
  assert.strictEqual(h.httpCalls.length, 1, "an enabled change checks immediately");
  const saved = JSON.parse(h.fs.store[h.remindersFile]);
  assert.deepStrictEqual({ enabled: saved.enabled, days: saved.days }, { enabled: true, days: 7 });
  setReminders(null, { enabled: false });
  assert.strictEqual(h.httpCalls.length, 1, "a disabled change does not check");
});

// ---- prefs:set-workspace：trim + 日志 ---------------------------------------------

test("prefs:set-workspace trims the report and logs it", () => {
  const h = makeHarness();
  h.io.registerIpc(h.ipcMain);
  const setWorkspace = h.ipcHandlers.get("prefs:set-workspace");
  assert.deepStrictEqual(setWorkspace(null, "  personal  "), { workspace: "personal" });
  assert.strictEqual(h.io.workspace(), "personal");
  assert.ok(h.logs.includes("Workspace reported by renderer: personal"));
  assert.deepStrictEqual(setWorkspace(null, null), { workspace: "" });
  assert.ok(h.logs.includes("Workspace reported by renderer: (default)"));
});

// ---- timer：幂等 / 停止 / 重新启动 ------------------------------------------------

test("startTimer is idempotent; stopTimer clears exactly one timer", () => {
  const h = makeHarness();
  h.io.startTimer();
  assert.strictEqual(h.timers.setCount, 1);
  assert.strictEqual(h.timers.lastMs, 1000, "the injected interval is used");
  assert.strictEqual(h.httpCalls.length, 1, "start checks once");
  h.io.startTimer();
  assert.strictEqual(h.timers.setCount, 1, "a second start keeps a single timer");
  assert.strictEqual(h.httpCalls.length, 1, "a second start does not check again");
  h.io.stopTimer();
  assert.strictEqual(h.timers.clearCount, 1);
  h.io.stopTimer();
  assert.strictEqual(h.timers.clearCount, 1, "stop with no timer is a no-op");
  h.io.startTimer();
  assert.strictEqual(h.timers.setCount, 2, "after a stop a start creates a new timer");
});

// ---- check()：enabled 门 / 查询串 / 成功与静默路径 --------------------------------

test("check is a no-op while reminders are disabled", () => {
  const h = makeHarness({ fileContent: '{"enabled": false}' });
  h.io.loadState();
  h.io.check();
  assert.strictEqual(h.httpCalls.length, 0, "disabled means no request");
});

test("check queries /api/reminders/due with ws and days, then notifies", () => {
  const h = makeHarness();
  h.io.registerIpc(h.ipcMain);
  h.ipcHandlers.get("prefs:set-workspace")(null, "personal");
  h.ipcHandlers.get("prefs:set-reminders")(null, { days: 7 });
  assert.strictEqual(h.httpCalls.length, 1);
  const call = h.httpCalls[0];
  assert.strictEqual(call.url, `http://127.0.0.1:${BACKEND_PORT}/api/reminders/due?ws=personal&days=7`);
  assert.strictEqual(call.options.timeout, 4000, "the request keeps its 4s timeout");
  answer(call, { body: dueBody([{ id: "A001", 公司: "Acme", daysLeft: 1 }]) });
  assert.strictEqual(h.notifications.length, 1);
  assert.ok(h.notifications[0].shown, "the notification is shown");
  assert.ok(h.logs.some((line) => /^Reminder shown: \d+ line\(s\)$/.test(line)));
  const saved = JSON.parse(h.fs.store[h.remindersFile]);
  assert.deepStrictEqual(saved.notified, { "todos:A001": todayKey() });
});

test("check stays silent on non-200 responses, bad JSON and request errors", () => {
  const h = makeHarness();
  h.io.startTimer();
  const call = h.httpCalls[0];
  answer(call, { statusCode: 500 });
  answer(call, { statusCode: 200, body: "<html>not json</html>" });
  assert.strictEqual(h.notifications.length, 0, "bad responses never notify");
  assert.doesNotThrow(() => call.req.handlers.error(new Error("ECONNREFUSED")));
  call.req.handlers.timeout();
  assert.strictEqual(call.req.handlers.destroyed, true, "a timeout destroys the request");
});

test("an item already reported today stays quiet; a garbage notified falls back to empty", () => {
  const todos = [{ id: "A001", 公司: "Acme", daysLeft: 1 }];
  const reported = makeHarness({ fileContent: JSON.stringify({ notified: { "todos:A001": todayKey() } }) });
  reported.io.loadState();
  reported.io.check();
  answer(reported.httpCalls[0], { body: dueBody(todos) });
  assert.strictEqual(reported.notifications.length, 0, "already reported today");
  const garbage = makeHarness({ fileContent: JSON.stringify({ notified: "yesterday" }) });
  garbage.io.loadState();
  garbage.io.check();
  answer(garbage.httpCalls[0], { body: dueBody(todos) });
  assert.strictEqual(garbage.notifications.length, 1, "garbage is dropped, so it notifies");
});

// ---- showDueNotification：点击回调 ------------------------------------------------

test("clicking the notification focuses the window and sends reminder:focus", () => {
  const h = makeHarness();
  const win = {
    shown: false,
    focused: false,
    sent: [],
    show() { this.shown = true; },
    focus() { this.focused = true; },
    webContents: { send: (channel, payload) => win.sent.push({ channel, payload }) },
  };
  h.windows.push(win);
  h.io.showDueNotification({
    counts: { todos: 1, talks: 0, overdue: 0 },
    todos: [{ id: "A001", 公司: "Acme", 岗位: "Dev", date: "2026-09-25", 说明: "", daysLeft: 1 }],
  });
  assert.strictEqual(h.notifications.length, 1);
  h.notifications[0].handlers.click();
  assert.ok(win.shown && win.focused, "the window is brought to front");
  assert.deepStrictEqual(win.sent, [{ channel: "reminder:focus", payload: { id: "A001" } }]);
});

test("clicking with no window open does not throw", () => {
  const h = makeHarness();
  h.io.showDueNotification({ counts: {}, todos: [] });
  assert.doesNotThrow(() => h.notifications[0].handlers.click());
});
