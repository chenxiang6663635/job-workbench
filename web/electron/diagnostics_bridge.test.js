// 「复制诊断信息」弹窗的调度层（2026-10-28 审计 §七 第 2 条）。
//
// 背景：端口冲突提示此前走 `dialog.showErrorBox`——**不能带按钮**，所以用户拿不到
// 「复制诊断」这个出口；而冲突当下的弹窗正是用户唯一会看的界面。改成 `notifyUser`
// 之后还必须解决第二件事：它在 `app.quit()` 之前只是「把弹窗排上队」，直接退出会把
// 弹窗一起收走。所以 `notifyUser` 要**返回一个 promise**，调用方等弹窗关掉再退。
//
// 本模块不 require("electron")：dialog / clipboard / shell 全部注入，这里用假件。
const test = require("node:test");
const assert = require("node:assert/strict");
const os = require("os");
const path = require("path");
const { createDiagnosticsBridge } = require("./diagnostics_bridge");

function makeBridge({ response = 1 } = {}) {
  const dialogs = [];
  const copied = [];
  const bridge = createDiagnosticsBridge({
    app: { getVersion: () => "26.10.0", getPath: () => path.join("C:", "tmp") },
    log: () => {},
    tFor: () => (key) => (key === "copyDiag" ? "Copy diagnostics" : key),
    resolvedLang: () => "en",
    logFilePath: () => path.join("C:", "tmp", "app.log"),
    BrowserWindow: { getAllWindows: () => [] },
    dialog: {
      showMessageBox: (opts) => {
        dialogs.push(opts);
        return Promise.resolve({ response });
      },
    },
    clipboard: { writeText: (text) => copied.push(text) },
    shell: { openPath: () => Promise.resolve("") },
    os,
    fs: { readFileSync: () => "line1\n[backend-err] boom\n" },
  });
  return { bridge, dialogs, copied };
}

test("notifyUser: returns a thenable so the caller can quit after the dialog closes", async () => {
  const { bridge, dialogs } = makeBridge({ response: 1 });
  const pending = bridge.notifyUser("title", "message", { withDiagnostics: true });
  assert.equal(typeof pending.then, "function",
    "notifyUser must be awaitable, or app.quit() closes the dialog before it is read");
  await pending;
  assert.equal(dialogs.length, 1);
  assert.deepEqual(dialogs[0].buttons, ["Copy diagnostics", "OK"]);
});

test("notifyUser: the diagnostics button copies a report and the promise still resolves", async () => {
  const { bridge, copied, dialogs } = makeBridge({ response: 0 });
  await bridge.notifyUser("title", "message", { withDiagnostics: true });
  assert.deepEqual(dialogs[0].buttons, ["Copy diagnostics", "OK"]);
  assert.equal(copied.length, 1, "the first button must copy the diagnostics report");
  assert.ok(copied[0].includes("[backend-err] boom"), copied[0]);
});

test("notifyUser: without withDiagnostics there is only OK and nothing is copied", async () => {
  const { bridge, dialogs, copied } = makeBridge({ response: 0 });
  await bridge.notifyUser("title", "message");
  assert.deepEqual(dialogs[0].buttons, ["OK"]);
  assert.equal(copied.length, 0);
});

/**
 * 用「手动落定」的假 dialog 造真实时序：每次 showMessageBox 存一个 deferred。
 *
 * 为什么不用 makeBridge：那个版本的 showMessageBox 立刻 resolve，测不出
 * 「外层等没等第二个弹窗」——这正是 3.1 的缺口所在。
 */
function makeDeferredBridge() {
  const dialogs = [];
  const pending = [];
  const bridge = createDiagnosticsBridge({
    app: { getVersion: () => "26.11.0", getPath: () => path.join("C:", "tmp") },
    log: () => {},
    tFor: () => (key) => (key === "copyDiag" ? "Copy diagnostics" : key),
    resolvedLang: () => "en",
    logFilePath: () => path.join("C:", "tmp", "app.log"),
    BrowserWindow: { getAllWindows: () => [] },
    dialog: {
      showMessageBox: (opts) => {
        dialogs.push(opts);
        return new Promise((resolve, reject) => pending.push({ opts, resolve, reject }));
      },
    },
    clipboard: { writeText: () => {} },
    shell: { openPath: () => Promise.resolve("") },
    os,
    fs: { readFileSync: () => "line1\n" },
  });
  return { bridge, dialogs, pending };
}

/** 让已排队的 microtask / then 链推进一轮（比 setTimeout(0) 更轻）。 */
const tick = () => new Promise((resolve) => setImmediate(resolve));

test("notifyUser: the outer promise settles only after the 'copied' dialog closes", async () => {
  const { bridge, pending } = makeDeferredBridge();
  let settled = false;
  const outer = bridge.notifyUser("title", "message", { withDiagnostics: true });
  outer.then(() => { settled = true; });

  await tick();
  assert.equal(pending.length, 1, "the first dialog should be open");

  // 用户点了「Copy diagnostics」——第二个弹窗（已复制）打开
  pending[0].resolve({ response: 0 });
  await tick();

  assert.equal(pending.length, 2, "the 'copied' dialog should be open now");
  assert.equal(settled, false,
    "must not settle while the 'copied' dialog is still open (app.quit() would close it)");

  pending[1].resolve({ response: 0 });
  await outer;
  assert.equal(settled, true);
});

test("notifyUser: a failing 'copied' dialog does not reject the outer promise", async () => {
  const { bridge, pending } = makeDeferredBridge();
  const outer = bridge.notifyUser("title", "message", { withDiagnostics: true });

  await tick();
  pending[0].resolve({ response: 0 });
  await tick();
  assert.equal(pending.length, 2);

  // 第二个弹窗失败（例如窗口已销毁）——通知不该因此变成第二次崩溃，
  // 调用方的 .then(app.quit) 必须照常执行
  pending[1].reject(new Error("window destroyed"));
  await outer;
});

test("notifyUser: OK (no copy) settles on the first dialog alone", async () => {
  const { bridge, pending } = makeDeferredBridge();
  let settled = false;
  const outer = bridge.notifyUser("title", "message", { withDiagnostics: true });
  outer.then(() => { settled = true; });

  await tick();
  pending[0].resolve({ response: 1 });   // 第二个按钮 = OK
  await outer;
  assert.equal(settled, true);
  assert.equal(pending.length, 1, "no second dialog when the user does not copy");
});
