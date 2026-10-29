// Python 探测的测试（`node web/electron/python_detect.test.js`，CI 也跑）。
//
// 从 backend_process.test.js 搬出来（2026-10-28）：那边越过 315 登记水位，
// 而这两个函数已抽成独立模块，测试跟着被测对象走更合理。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode 会拦中文串）。
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const { createPythonDetector } = require("./python_detect");

/** 用最小依赖构造探测器；返回 logs 便于断言「选择了谁 / 拒绝了谁」。 */
function mk({ env = {}, platform = "linux", fs, childProcess } = {}) {
  const logs = [];
  const d = createPythonDetector({
    env,
    platform,
    path,
    fs: fs || { existsSync: () => false },
    childProcess: childProcess || {
      execFileSync: () => {
        throw new Error("unexpected probe: no candidate should be tried");
      },
    },
    log: (m) => logs.push(m),
  });
  return { ...d, logs };
}

test("findOnPath: first PATH entry wins; win32 tries .exe then .cmd then bare name", () => {
  const hit = path.join("/usr/local/bin", "python");
  const posix = mk({ env: { PATH: "/usr/local/bin:/usr/bin" }, fs: { existsSync: (p) => p === hit } });
  assert.equal(posix.findOnPath("python"), hit);

  const dir = "C:\\tools";
  const exe = path.join(dir, "python.exe");
  const cmd = path.join(dir, "python.cmd");
  // 只有 .cmd 存在：.exe 未命中后继续找，而不是直接放弃
  const cmdOnly = mk({
    platform: "win32",
    env: { PATH: `C:\\empty;${dir}` },
    fs: { existsSync: (p) => p === cmd },
  });
  assert.equal(cmdOnly.findOnPath("python"), cmd);

  // .exe 与 .cmd 同时存在：按扩展名顺序取 .exe
  const both = mk({
    platform: "win32",
    env: { PATH: dir },
    fs: { existsSync: (p) => p === exe || p === cmd },
  });
  assert.equal(both.findOnPath("python"), exe);

  assert.equal(mk({ env: { PATH: "/nope" } }).findOnPath("python"), null, "no match means null");
});

test("detectPython: JOBWS_PYTHON first, skips unusable candidates, null when none", () => {
  const tries = [];
  const first = mk({
    env: { JOBWS_PYTHON: "custom-py", PATH: "" },
    childProcess: { execFileSync: (cmd) => (tries.push(cmd), Buffer.from("ok")) },
  });
  assert.equal(first.detectPython(), "custom-py");
  assert.deepEqual(tries, ["custom-py"], "a hit ends the search");
  assert.ok(first.logs.some((l) => l.includes("Using Python: custom-py")), "the choice is logged");

  const py = path.join("/opt/py", "python");
  const py3 = path.join("/opt/py", "python3");
  const fallbackTries = [];
  const fallback = mk({
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
  assert.equal(fallback.detectPython(), py3);
  assert.deepEqual(fallbackTries, ["broken-py", py, py3], "candidates are tried in order");
  assert.ok(
    fallback.logs.some((l) => l.includes(`Python not usable: ${py}`)),
    "a rejected candidate is logged",
  );
  assert.ok(
    fallback.logs.every((l) => !l.includes("more detail")),
    "only the first error line is logged",
  );

  // 没有候选可试 → null（默认 execFileSync 会抛，证明没有盲探测）
  assert.equal(mk({ env: { PATH: "" } }).detectPython(), null);
});
