// 健康探测与就绪等待的单测（2026-10-28 从 `backend_process.test.js` 拆出：那个文件
// 越过 300 行规模预算，按「健康探测」/「进程启停」两个职责分开）。
//
// 钉住的行为：`checkHealth` 的六种 reason、done 门（双事件只回调一次）、`waitBackendReady`
// 只认本窗口拉起的那个实例。fake 进程 / fake http / deps 组装见
// `backend_process_test_support.js`。
//
// 断言消息用英文：electron 树的字符串口径是英文（`check_i18n_hardcode` 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const test = require("node:test");
const assert = require("node:assert/strict");
const { INSTANCE_ID } = require("./backend_process");
const { makeDeps, fakeHealthHttp, collect } = require("./backend_process_test_support");

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
