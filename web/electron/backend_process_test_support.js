// backend_process 单测的共享替身（2026-10-28 从 `backend_process.test.js` 拆出）。
//
// 拆的理由：那个文件越过 300 行规模预算，而「健康探测」与「进程启停」本来就是两件事，
// 于是拆成 `backend_process_health.test.js` 与 `backend_process.test.js`。fake 进程 /
// fake http / deps 组装两边都要用，放独立模块——各抄一份之后「改一处忘另一处」是必然。

const path = require("path");
const assert = require("node:assert/strict");
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
    // 与 diagnostics_bridge.notifyUser 的真实契约一致：它返回 promise（2026-10-28 起，
    // 调用方靠它把 app.quit() 延到弹窗关闭之后）——替身返回 undefined 会让调用处炸。
    notifyUser: (title, message, opts) => {
      notifications.push({ title, message, opts });
      return Promise.resolve();
    },
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

/**
 * 同步收集一次回调的结果（fake 环境里事件都是同步触发的）。
 *
 * **只收第一个参数**——要断言 `reason` 就别用它（会把第二个参数吞掉，这正是
 * 2026-10-28 审计里「timeout 的 reason 没被钉住」的成因）；改用内联 `(ok, reason) => …`。
 */
function collect(run) { const out = []; run((v) => out.push(v)); return out; }

module.exports = { EXE, fakeProc, makeDeps, exeHarness, fakeHealthHttp, collect };
