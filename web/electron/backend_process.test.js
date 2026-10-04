// 后端进程管理的单测（`node web/electron/backend_process.test.js`，CI 也跑这一步）：用注入的
// fake（fs / http / childProcess / app）钉住搬运中必须一致的行为——探测优先级、健康检查
// done 门（双事件只回调一次）、start/stop 空守卫、win32 taskkill、exit 三分支与提示文案。
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { createBackendProcess } = require("./backend_process");
const EXE = path.join("app", "resources", "backend", "job-workbench-backend.exe"); // 打包形态 exe 落点

/** 最小可用的后端进程对象：记录 stdout/stderr 与生命周期回调，供测试主动触发。 */
function fakeProc(pid = 4242) {
  const events = {};
  const streams = { stdout: {}, stderr: {} };
  return {
    pid,
    stdout: { on: (e, fn) => (streams.stdout[e] = fn) },
    stderr: { on: (e, fn) => (streams.stderr[e] = fn) },
    on: (e, fn) => (events[e] = fn),
    kill: () => {},
    fire: (e, ...args) => events[e] && events[e](...args),
    out: (chunk) => streams.stdout.data(chunk),
    err: (chunk) => streams.stderr.data(chunk),
  };
}

/** 组装测试用 deps：默认「不许被调用」/「无命中」；fs / http / childProcess 支持按键增量覆盖。 */
function makeDeps(overrides = {}) {
  const logs = [], notifications = [], quits = [];
  const base = {
    app: { getVersion: () => "26.9.0", quit: () => quits.push(true) },
    log: (msg) => logs.push(String(msg)),
    notifyUser: (title, message, opts) => notifications.push({ title, message, opts }),
    tFor: () => (key) => key,
    resolvedLang: () => "en",
    backendDir: path.join("repo", "web", "backend"),
    fs: { existsSync: () => false },
    path,
    http: { get: () => assert.fail("unexpected http.get") },
    childProcess: {
      spawn: () => assert.fail("unexpected spawn"),
      execFileSync: () => assert.fail("unexpected execFileSync"),
      execSync: () => assert.fail("unexpected execSync"),
    },
    env: {},
    platform: "linux",
    resourcesPath: path.join("app", "resources"),
  };
  const deps = { ...base, ...overrides };
  for (const key of ["fs", "http", "childProcess"]) {
    if (overrides[key]) deps[key] = { ...base[key], ...overrides[key] };
  }
  return { bp: createBackendProcess(deps), logs, notifications, quits };
}

/** 打包 exe 存在的场景：fs 只认 EXE，spawn 记录进 spawned。 */
function exeHarness({ childProcess = {}, ...rest } = {}) {
  const spawned = [];
  const deps = makeDeps({
    fs: { existsSync: (p) => p === EXE },
    ...rest,
    childProcess: {
      spawn: (cmd, args, opts) => {
        const proc = fakeProc();
        spawned.push({ cmd, args, opts, proc });
        return proc;
      },
      ...childProcess,
    },
  });
  return { ...deps, spawned };
}

/** checkHealth 用的假 http：手动回响应 / 触发 error 与 timeout。 */
function fakeHealthHttp() {
  const state = { url: null, opts: null, destroyed: 0, respond: null };
  const reqEvents = {};
  const resEvents = {};
  const res = { statusCode: 0, on: (e, fn) => (resEvents[e] = fn) };
  const req = { on: (e, fn) => (reqEvents[e] = fn), destroy: () => (state.destroyed += 1) };
  return {
    state,
    http: { get: (url, opts, cb) => (state.url = url, state.opts = opts, state.respond = cb, req) },
    respond: (statusCode, body) => {
      res.statusCode = statusCode;
      state.respond(res);
      if (resEvents.data) resEvents.data(body);
      if (resEvents.end) resEvents.end();
    },
    fire: (e) => reqEvents[e] && reqEvents[e](),
  };
}
/** 同步收集一次回调的结果（fake 环境里事件都是同步触发的）。 */
function collect(run) { const out = []; run((v) => out.push(v)); return out; }

test("exposes the backend constants verbatim", () => {
  const { bp } = makeDeps();
  assert.equal(bp.BACKEND_PORT, 8765);
  assert.equal(bp.HEALTH_URL, "http://127.0.0.1:8765/api/health");
  assert.equal(bp.HEARTBEAT_INTERVAL, 500);
  assert.equal(bp.HEARTBEAT_TIMEOUT, 30000);
});

test("findOnPath: first PATH entry wins; win32 tries .exe then .cmd then bare name", () => {
  const hit = path.join("/usr/local/bin", "python");
  const posix = makeDeps({ env: { PATH: "/usr/local/bin:/usr/bin" }, fs: { existsSync: (p) => p === hit } });
  assert.equal(posix.bp.findOnPath("python"), hit);
  const dir = "C:\\tools";
  const exe = path.join(dir, "python.exe");
  const cmd = path.join(dir, "python.cmd");
  // 只有 .cmd 存在：.exe 未命中后继续找，而不是直接放弃
  const cmdOnly = makeDeps({ platform: "win32", env: { PATH: `C:\\empty;${dir}` }, fs: { existsSync: (p) => p === cmd } });
  assert.equal(cmdOnly.bp.findOnPath("python"), cmd);
  // .exe 与 .cmd 同时存在：按扩展名顺序取 .exe
  const both = makeDeps({ platform: "win32", env: { PATH: dir }, fs: { existsSync: (p) => p === exe || p === cmd } });
  assert.equal(both.bp.findOnPath("python"), exe);
  assert.equal(makeDeps({ env: { PATH: "/nope" } }).bp.findOnPath("python"), null, "no match means null");
});

test("detectPython: JOBWS_PYTHON first, skips unusable candidates, null when none", () => {
  const tries = [];
  const first = makeDeps({
    env: { JOBWS_PYTHON: "custom-py", PATH: "" },
    childProcess: { execFileSync: (cmd) => (tries.push(cmd), Buffer.from("ok")) },
  });
  assert.equal(first.bp.detectPython(), "custom-py");
  assert.deepEqual(tries, ["custom-py"], "a hit ends the search");
  assert.ok(first.logs.some((l) => l.includes("Using Python: custom-py")), "the choice is logged");
  const py = path.join("/opt/py", "python");
  const py3 = path.join("/opt/py", "python3");
  const fallbackTries = [];
  const fallback = makeDeps({
    env: { JOBWS_PYTHON: "broken-py", PATH: "/opt/py" },
    fs: { existsSync: (p) => p === py || p === py3 },
    childProcess: {
      execFileSync: (cmd) => {
        fallbackTries.push(cmd);
        if (cmd === "broken-py") throw new Error("not found");
        if (cmd === py) throw new Error("ModuleNotFoundError: fastapi\nmore detail");
        return Buffer.from("ok");
      },
    },
  });
  assert.equal(fallback.bp.detectPython(), py3);
  assert.deepEqual(fallbackTries, ["broken-py", py, py3]);
  assert.ok(fallback.logs.some((l) => l.includes(`Python not usable: ${py}`)), "a rejected candidate is logged");
  assert.ok(fallback.logs.every((l) => !l.includes("more detail")), "only the first error line is logged");
  // 没有候选可试 → null（默认 execFileSync 会 assert.fail，证明没有盲探测）
  assert.equal(makeDeps({ env: { PATH: "" } }).bp.detectPython(), null);
});
test("findBackendExe: packaged layout only, never on source runs", () => {
  assert.equal(exeHarness().bp.findBackendExe(), EXE);
  assert.equal(makeDeps().bp.findBackendExe(), null);
});

test("checkHealth: 200 + 'ok' means ready; 500 / missing 'ok' means not ready", () => {
  const h = fakeHealthHttp();
  const { bp } = makeDeps({ http: h.http });
  const results = collect((cb) => bp.checkHealth(cb));
  assert.equal(h.state.url, bp.HEALTH_URL);
  assert.equal(h.state.opts.timeout, 1000);
  h.respond(200, "ok");
  assert.deepEqual(results, [true]);
  // 状态码不对 / 200 但正文还没有 ok —— 都算未就绪
  for (const [status, body] of [[500, "ok"], [200, "starting"]]) {
    const h2 = fakeHealthHttp();
    const b = makeDeps({ http: h2.http });
    const results2 = collect((cb) => b.bp.checkHealth(cb));
    h2.respond(status, body);
    assert.deepEqual(results2, [false], `${status} + "${body}" must not count as ready`);
  }
});

test("checkHealth: the done gate collapses racing events into one callback", () => {
  const h = fakeHealthHttp();
  const { bp } = makeDeps({ http: h.http });
  const results = collect((cb) => bp.checkHealth(cb));
  h.respond(200, "ok");
  h.fire("error"); // 迟到的事件：done 门拦下，否则 waitBackendReady 双轮询 → 双窗口
  h.fire("timeout");
  assert.deepEqual(results, [true]);
  const h2 = fakeHealthHttp();
  const b = makeDeps({ http: h2.http });
  const second = collect((cb) => b.bp.checkHealth(cb));
  h2.fire("error");
  h2.fire("timeout");
  assert.deepEqual(second, [false]);
  assert.equal(h2.state.destroyed, 1, "the timeout still destroys the request");
});

test("waitBackendReady: a healthy backend flips ready and calls back", () => {
  const h = fakeHealthHttp();
  const { bp, logs } = makeDeps({ http: h.http });
  const called = collect((cb) => bp.waitBackendReady(() => cb(true)));
  h.respond(200, "ok");
  assert.deepEqual(called, [true]);
  assert.equal(bp.isReady(), true);
  assert.ok(logs.some((l) => l.includes("Backend ready")));
});

test("backendEnv: forces JOBWS_NO_BROWSER=1 and injects the app version", () => {
  const { bp } = makeDeps({ env: { PATH: "x", JOBWS_NO_BROWSER: "0" } });
  assert.deepEqual(bp.backendEnv(), { PATH: "x", JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: "26.9.0" });
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
  assert.deepEqual(call.opts.env, { JOBWS_NO_BROWSER: "1", JOBWS_APP_VERSION: "26.9.0" });
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

test("startBackend: with no exe and no usable Python it notifies and quits", () => {
  const { bp, notifications, quits } = makeDeps({ env: { PATH: "" } });
  bp.startBackend();
  assert.equal(notifications.length, 1);
  assert.equal(notifications[0].title, "backendMissingPythonTitle");
  assert.equal(notifications[0].message, "backendMissingPythonMessage");
  assert.deepEqual(notifications[0].opts, { withDiagnostics: true });
  assert.equal(quits.length, 1);
  assert.equal(bp.isRunning(), false);
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
