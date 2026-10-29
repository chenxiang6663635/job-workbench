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
  const { bridge, copied } = makeBridge({ response: 0 });
  await bridge.notifyUser("title", "message", { withDiagnostics: true });
  assert.equal(copied.length, 1, "the first button must copy the diagnostics report");
  assert.ok(copied[0].includes("[backend-err] boom"), copied[0]);
});

test("notifyUser: without withDiagnostics there is only OK and nothing is copied", async () => {
  const { bridge, dialogs, copied } = makeBridge({ response: 0 });
  await bridge.notifyUser("title", "message");
  assert.deepEqual(dialogs[0].buttons, ["OK"]);
  assert.equal(copied.length, 0);
});
