// navigation 接线层的无依赖单测（node:test）：`node web/electron/navigation.test.js`。
// 覆盖五条安全边界：同源导航放行 / 前缀伪装与跨源被拦 / 外链恒 deny 且仅 https 交系统
// 浏览器 / CSP 只加给本机后端源 / CSP 安装抛错被吞。session、shell 用假对象注入——这
// 正是本模块不 require("electron") 的收益：安全判断在 node 下可测。
//
// 断言消息与字符串用英文（electron 树的字符串口径是英文，check_i18n_hardcode.py 会把
// 中文串按界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const { createNavigation } = require("./navigation");

const PORT = 8765;
const ORIGIN = `http://127.0.0.1:${PORT}`;

// ---- 假对象 -------------------------------------------------------------------

function makeLogs() {
  const lines = [];
  return { lines, log: (msg) => lines.push(String(msg)) };
}

function makeShell() {
  return {
    opened: [],
    openExternal(url) {
      this.opened.push(url);
      return Promise.resolve();
    },
  };
}

function makeSession({ failOnRegister = false } = {}) {
  const handlers = [];
  return {
    handlers,
    defaultSession: {
      webRequest: {
        onHeadersReceived(handler) {
          if (failOnRegister) throw new Error("session unavailable");
          handlers.push(handler);
        },
      },
    },
  };
}

function makeWindow() {
  const events = {};
  return {
    events,
    webContents: {
      on(name, handler) {
        (events[name] = events[name] || []).push(handler);
      },
      setWindowOpenHandler(handler) {
        events.openHandler = handler;
      },
    },
  };
}

function makeNavigation(overrides = {}) {
  const logs = makeLogs();
  const shell = makeShell();
  const session = makeSession();
  const nav = createNavigation({
    session,
    shell,
    log: logs.log,
    backendPort: PORT,
    ...overrides,
  });
  return { nav, logs, shell, session };
}

function navEvent() {
  return {
    prevented: false,
    preventDefault() {
      this.prevented = true;
    },
  };
}

// ---- 导出结构 -----------------------------------------------------------------

test("exposes installCsp and wireWindow", () => {
  const { nav } = makeNavigation();
  assert.equal(typeof nav.installCsp, "function");
  assert.equal(typeof nav.wireWindow, "function");
});

// ---- 导航：同源放行 -----------------------------------------------------------

test("allows same-origin navigation and redirects", () => {
  const { nav, logs } = makeNavigation();
  const win = makeWindow();
  nav.wireWindow(win);

  const navigate = navEvent();
  win.events["will-navigate"][0](navigate, `${ORIGIN}/index.html#/dashboard`);
  assert.equal(navigate.prevented, false, "same-origin navigation must pass");

  const redirect = navEvent();
  win.events["will-redirect"][0](redirect, `${ORIGIN}/login`);
  assert.equal(redirect.prevented, false, "same-origin redirect must pass");

  assert.deepEqual(logs.lines, [], "nothing is logged for allowed navigations");
});

// ---- 导航：前缀伪装 / 跨源被拦 -------------------------------------------------

test("blocks lookalike and cross-origin navigations", () => {
  const { nav, logs } = makeNavigation();
  const win = makeWindow();
  nav.wireWindow(win);

  const navigate = navEvent();
  win.events["will-navigate"][0](navigate, "http://127.0.0.1:8765.evil.com/steal");
  assert.equal(navigate.prevented, true, "prefix lookalike host must not pass");
  assert.ok(
    logs.lines.some((l) => l.includes("Blocked navigation to http://127.0.0.1:8765.evil.com/steal")),
    "blocked navigation must be logged",
  );

  const redirect = navEvent();
  win.events["will-redirect"][0](redirect, "https://evil.example/steal");
  assert.equal(redirect.prevented, true, "cross-origin redirect must not pass");
  assert.ok(
    logs.lines.some((l) => l.includes("Blocked redirect to https://evil.example/steal")),
    "blocked redirect must be logged",
  );
});

// ---- 外链：恒 deny，仅 https 交系统浏览器 --------------------------------------

test("external links are always denied; only https opens in the shell", () => {
  const { nav, logs, shell } = makeNavigation();
  const win = makeWindow();
  nav.wireWindow(win);
  const open = win.events.openHandler;

  assert.deepEqual(open({ url: "https://mail.google.com/u/0/" }), { action: "deny" });
  assert.deepEqual(shell.opened, ["https://mail.google.com/u/0/"], "https opens externally");

  assert.deepEqual(open({ url: "http://example.com/" }), { action: "deny" });
  assert.deepEqual(open({ url: "file:///C:/Windows/System32/calc.exe" }), { action: "deny" });
  assert.deepEqual(open({ url: "javascript:alert(1)" }), { action: "deny" });
  assert.equal(shell.opened.length, 1, "only https reaches the shell");
  assert.ok(logs.lines.some((l) => l.includes("Blocked external open of http://example.com/")));
});

test("a failing shell.openExternal is logged, not thrown", async () => {
  const shell = { openExternal: () => Promise.reject(new Error("no browser")) };
  const { nav, logs } = makeNavigation({ shell });
  const win = makeWindow();
  nav.wireWindow(win);

  assert.deepEqual(win.events.openHandler({ url: "https://example.com/" }), { action: "deny" });
  await new Promise((resolve) => setImmediate(resolve)); // 让 .catch 落地
  assert.ok(logs.lines.some((l) => l.includes("Failed to open external URL: no browser")));
});

// ---- CSP：只加给本机后端源 -----------------------------------------------------

test("CSP is attached only to the local backend origin", () => {
  const { nav, session } = makeNavigation();
  nav.installCsp();
  assert.equal(session.handlers.length, 1, "one onHeadersReceived handler is registered");
  const onHeaders = session.handlers[0];

  let backendResult;
  onHeaders({ url: `${ORIGIN}/index.html`, responseHeaders: { "X-Test": ["1"] } }, (res) => {
    backendResult = res;
  });
  const csp = backendResult.responseHeaders["Content-Security-Policy"];
  assert.ok(Array.isArray(csp) && csp.length === 1, "CSP header is set for the backend origin");
  assert.ok(csp[0].includes("default-src 'self'"), "policy content is carried along");
  assert.deepEqual(backendResult.responseHeaders["X-Test"], ["1"], "other headers pass through");

  let foreignResult;
  onHeaders({ url: "https://example.com/x.js", responseHeaders: { "X-Test": ["2"] } }, (res) => {
    foreignResult = res;
  });
  assert.equal(
    "Content-Security-Policy" in foreignResult.responseHeaders,
    false,
    "no CSP outside the backend origin",
  );
  assert.deepEqual(foreignResult.responseHeaders, { "X-Test": ["2"] });
});

test("CSP install failure is swallowed and logged", () => {
  const logs = makeLogs();
  const nav = createNavigation({
    session: makeSession({ failOnRegister: true }),
    shell: makeShell(),
    log: logs.log,
    backendPort: PORT,
  });
  assert.doesNotThrow(() => nav.installCsp());
  assert.ok(logs.lines.some((l) => l.includes("CSP install failed: session unavailable")));
});

// ---- 注入契约：urlGuard 可替换（默认 require("./url_guard")） --------------------

test("uses the injected urlGuard when provided", () => {
  const calls = [];
  const urlGuard = {
    isAllowedNavigation(url, origin) {
      calls.push({ url, origin });
      return true; // 注入的守卫说放行：证明调用的是注入体，不是内置实现
    },
    isSafeExternalUrl: () => false,
  };
  const nav = createNavigation({
    session: makeSession(),
    shell: makeShell(),
    log: makeLogs().log,
    backendPort: PORT,
    urlGuard,
  });
  const win = makeWindow();
  nav.wireWindow(win);

  const event = navEvent();
  win.events["will-navigate"][0](event, "https://elsewhere.example/");
  assert.equal(event.prevented, false);
  assert.deepEqual(calls, [{ url: "https://elsewhere.example/", origin: ORIGIN }]);
});
