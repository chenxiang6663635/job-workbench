// 后端进程管理的单测（`node web/electron/backend_process.test.js`，CI 也跑这一步）：用注入的
// fake（fs / http / childProcess / app）钉住搬运中必须一致的行为——探测优先级、健康检查
// done 门（双事件只回调一次）、start/stop 空守卫、win32 taskkill、exit 三分支与提示文案。
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("path");
const { createBackendProcess, decideStartupAction, INSTANCE_ID } = require("./backend_process");
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
    fire: (e, arg) => reqEvents[e] && reqEvents[e](arg),
  };
}
/** 同步收集一次回调的结果（fake 环境里事件都是同步触发的）。 */
function collect(run) { const out = []; run((v) => out.push(v)); return out; }

test("findBackendExe: packaged layout only, never on source runs", () => {
  assert.equal(exeHarness().bp.findBackendExe(), EXE);
  assert.equal(makeDeps().bp.findBackendExe(), null);
});

test("checkHealth: (ok, reason) — reason distinguishes six outcomes", () => {
  const probe = (status, body, expectInstance) => {
    const h = fakeHealthHttp();
    const { bp } = makeDeps({ http: h.http });
    const out = [];
    bp.checkHealth((ok, reason) => out.push([ok, reason]), expectInstance);
    h.respond(status, body);
    return out;
  };
  const okBody = JSON.stringify({ status: "ok", service: "jobws" });

  assert.deepEqual(probe(200, okBody), [[true, "ok"]]);
  // 非 200 → status
  assert.deepEqual(probe(500, okBody), [[false, "status"]]);
  // 200 但身份不符 → identity（2026-10-28 审计的原始反例）
  assert.deepEqual(probe(200, JSON.stringify({ status: "ok", service: "unrelated" })),
    [[false, "identity"]]);
  // 200 但缺 service（旧后端）→ identity，宁可等不到也不误连
  assert.deepEqual(probe(200, JSON.stringify({ status: "ok" })), [[false, "identity"]]);
  // 非 JSON / 只含 ok 字样 → identity
  assert.deepEqual(probe(200, "all ok"), [[false, "identity"]]);
  // 实例不匹配 → identity（另一个 jobws 实例）
  assert.deepEqual(
    probe(200, JSON.stringify({ status: "ok", service: "jobws", instance_id: "other" }), INSTANCE_ID),
    [[false, "identity"]]);
});

test("checkHealth: only an explicit connection refusal counts as refused", () => {
  // 2026-10-28 审计：此前所有 error 都归 refused，于是 ECONNRESET 被读成
  // 「端口空着，去启动」——新后端随后撞上已占用的端口，失败原因与真因无关。
  const fire = (err) => {
    const h = fakeHealthHttp();
    const { bp } = makeDeps({ http: h.http });
    const out = [];
    bp.checkHealth((ok, reason) => out.push([ok, reason]));
    h.fire("error", err);
    return out;
  };
  const withCode = (code) => Object.assign(new Error("x"), { code });

  assert.deepEqual(fire(withCode("ECONNREFUSED")), [[false, "refused"]]);
  assert.deepEqual(fire(withCode("ECONNRESET")), [[false, "error"]]);
  assert.deepEqual(fire(withCode("ETIMEDOUT")), [[false, "error"]]);
  // 没有 code 的 error（比如手工 reject）同样保守地归 error
  assert.deepEqual(fire(undefined), [[false, "error"]]);
});

test("checkHealth: an unanswered request reports the timeout reason", () => {
  // 2026-10-28 审计 §七 第 1 条剩下一处：timeout 分支此前只有「迟到事件不重复回调」
  // 与 destroyed 的断言，reason 字符串本身没被钉住（那条 [false] 来自先到的 error）。
  // 回归形态：reason 改错（例如退回 refused）→ decideStartupAction 会去启动新后端，
  // 撞上被占用的端口——与本轮修的 error 误分类同一类。
  const h = fakeHealthHttp();
  const { bp } = makeDeps({ http: h.http });
  const out = [];
  // 不能用 collect（它只收第一个参数——reason 会被吞掉，正是这条测试要钉的东西）
  bp.checkHealth((ok, reason) => out.push([ok, reason]));
  h.fire("timeout");
  assert.deepEqual(out, [[false, "timeout"]]);
});

test("checkHealth: the done gate collapses racing events into one callback", () => {
  const h = fakeHealthHttp();
  const { bp } = makeDeps({ http: h.http });
  const results = collect((cb) => bp.checkHealth(cb));
  h.respond(200, JSON.stringify({ status: "ok", service: "jobws" }));
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
  // 启动路径要求实例匹配：只认自己拉起的那个（响应里带 INSTANCE_ID）
  h.respond(200, JSON.stringify({ status: "ok", service: "jobws", instance_id: INSTANCE_ID }));
  assert.deepEqual(called, [true]);
  assert.equal(bp.isReady(), true);
  assert.ok(logs.some((l) => l.includes("Backend ready")));
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
