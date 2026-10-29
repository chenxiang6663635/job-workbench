// 后端进程启停的单测（`node web/electron/backend_process.test.js`，CI 也跑这一步）：用注入的
// fake（fs / http / childProcess / app）钉住搬运中必须一致的行为——探测优先级、start/stop
// 空守卫、win32 taskkill、exit 三分支与提示文案。
//
// 2026-10-28 拆出：健康探测（checkHealth / waitBackendReady）搬去
// `backend_process_health.test.js`，共享替身搬去 `backend_process_test_support.js`——
// 本文件越过 300 行规模预算，而这两块本来就是两件事。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { INSTANCE_ID } = require("./backend_process");
const { EXE, fakeProc, makeDeps, exeHarness } = require("./backend_process_test_support");

test("findBackendExe: packaged layout only, never on source runs", () => {
  assert.equal(exeHarness().bp.findBackendExe(), EXE);
  assert.equal(makeDeps().bp.findBackendExe(), null);
});

test("backendEnv: forces JOBWS_NO_BROWSER=1 and injects the app version", () => {
  const { bp } = makeDeps({ env: { PATH: "x", JOBWS_NO_BROWSER: "0" } });
  assert.deepEqual(bp.backendEnv(), {
    PATH: "x", JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: "26.9.0",
    JOBWS_INSTANCE_ID: INSTANCE_ID,
  });
});
test("backendEnv: reads env and the app version at call time, not at creation time", () => {
  let version = "1.0.0";
  let reads = 0;
  const env = { A: "1" };
  const { bp } = makeDeps({
    app: { getVersion: () => (reads += 1, version), quit: () => {} },
    env,
  });
  assert.equal(reads, 0, "creating the module must not touch Electron state");
  version = "2.0.0";
  env.LATE = "yes";
  assert.equal(bp.backendEnv().JOBWS_APP_VERSION, "2.0.0");
  assert.equal(bp.backendEnv().LATE, "yes");
  assert.equal(reads, 2);
});

test("startBackend: prefers the packaged exe, forwards output, keeps the empty guard", () => {
  const h = exeHarness();
  h.bp.startBackend();
  h.bp.startBackend(); // 已运行：空守卫直接返回
  assert.equal(h.spawned.length, 1);
  const call = h.spawned[0];
  assert.equal(call.cmd, EXE);
  assert.deepEqual(call.args, []);
  assert.equal(call.opts.cwd, path.dirname(EXE));
  assert.equal(call.opts.stdio, "pipe");
  assert.equal(call.opts.detached, false);
  assert.deepEqual(call.opts.env, {
    JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: "26.9.0",
    JOBWS_INSTANCE_ID: INSTANCE_ID,
  });
  assert.equal(h.bp.isRunning(), true);
  call.proc.out("booting");
  call.proc.err("traceback");
  assert.ok(h.logs.some((l) => l.includes("[backend] booting")));
  assert.ok(h.logs.some((l) => l.includes("[backend-err] traceback")));
});

test("startBackend: python fallback runs uvicorn from the backend dir", () => {
  const spawned = [];
  const { bp } = makeDeps({
    env: { JOBWS_PYTHON: "py" },
    childProcess: {
      spawn: (cmd, args, opts) => (spawned.push({ cmd, args, opts, proc: fakeProc() }), spawned.at(-1).proc),
      execFileSync: () => Buffer.from("ok"),
    },
  });
  bp.startBackend();
  assert.equal(spawned.length, 1);
  assert.equal(spawned[0].cmd, "py");
  assert.deepEqual(spawned[0].args, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", String(bp.BACKEND_PORT)]);
  assert.equal(spawned[0].opts.cwd, path.join("repo", "web", "backend"));
});

test("startBackend: with no exe and no usable Python it notifies, then quits after the dialog", async () => {
  const { bp, notifications, quits } = makeDeps({ env: { PATH: "" } });
  bp.startBackend();
  assert.equal(notifications.length, 1);
  assert.equal(notifications[0].title, "backendMissingPythonTitle");
  assert.equal(notifications[0].message, "backendMissingPythonMessage");
  assert.deepEqual(notifications[0].opts, { withDiagnostics: true });
  assert.equal(bp.isRunning(), false);
  // 退出必须等弹窗关掉（2026-10-28 审计）：紧跟着 quit 会把还没读的弹窗收走
  assert.equal(quits.length, 0, "must not quit before the dialog is dismissed");
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(quits.length, 1);
});

test("exit branches: early non-zero exit vs crash after ready", () => {
  const a = exeHarness();
  a.bp.startBackend();
  a.spawned[0].proc.fire("exit", 1);
  assert.equal(a.notifications.length, 1);
  assert.equal(a.notifications[0].title, "backendStartFailedTitle");
  assert.ok(a.notifications[0].message.includes("backendStartFailedDetail"));
  assert.equal(a.bp.isRunning(), false, "the process reference is cleared after exit");
  const b = exeHarness();
  b.bp.startBackend();
  b.bp.markReady();
  b.spawned[0].proc.fire("exit", 3);
  assert.equal(b.notifications[0].title, "backendDiedTitle");
});

test("stopBackend: win32 taskkill, a deliberate stop stays silent, never-reset ready", () => {
  const execCalls = [];
  const h = exeHarness({ platform: "win32", childProcess: { execSync: (cmd, opts) => execCalls.push({ cmd, opts }) } });
  h.bp.startBackend();
  h.bp.stopBackend();
  assert.deepEqual(execCalls, [{ cmd: "taskkill /pid 4242 /f /t", opts: { stdio: "ignore" } }]);
  assert.equal(h.bp.isRunning(), false);
  h.spawned[0].proc.fire("exit", 0);
  assert.deepEqual(h.notifications, [], "a stop we asked for must never show an error dialog");
  assert.ok(h.logs.some((l) => l.includes("Backend stopped by app, code=0")));
  const idle = makeDeps(); // 未启动：空守卫直接 return（默认 execSync = assert.fail 没被碰）
  idle.bp.stopBackend();
  assert.equal(idle.bp.isReady(), false);
  idle.bp.markReady();
  assert.equal(idle.bp.isReady(), true);
  idle.bp.stopBackend();
  assert.equal(idle.bp.isReady(), true, "backendReady is never reset");
});
