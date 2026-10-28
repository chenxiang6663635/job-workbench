// 后端身份判定与启动决策的单测（`node web/electron/backend_identity.test.js`，CI 也跑）。
//
// 与 backend_process.test.js 分开：那边测「拉起/停止进程」，这里测「连到哪个实例」。
// 两者是不同职责，混在一起时文件都逼近规模水位（2026-10-28 拆分）。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode 会拦中文串）。
const test = require("node:test");
const assert = require("node:assert/strict");

const {
  isHealthy, decideStartupAction, INSTANCE_ID, SERVICE_ID,
} = require("./backend_identity");

const body = (extra) => JSON.stringify({ status: "ok", service: SERVICE_ID, ...extra });

test("isHealthy: 200 + status:ok + service:jobws is ours", () => {
  assert.equal(isHealthy(200, body({})), true);
});

test("isHealthy: status ok but service is someone else is not ours", () => {
  // 2026-10-28 审计的原始反例：只验 status 时这个会被接受
  assert.equal(isHealthy(200, JSON.stringify({ status: "ok", service: "unrelated" })), false);
  // 缺 service（旧后端）同样不接受
  assert.equal(isHealthy(200, JSON.stringify({ status: "ok" })), false);
});

test("isHealthy: with expectInstance, only that instance counts", () => {
  assert.equal(isHealthy(200, body({ instance_id: INSTANCE_ID }), INSTANCE_ID), true);
  assert.equal(isHealthy(200, body({ instance_id: "someone-else" }), INSTANCE_ID), false,
    "another instance of the same product must not count as ours");
  // 不传 expectInstance：只验产品身份（复用路径，此时并不知道对方实例 id）
  assert.equal(isHealthy(200, body({ instance_id: "someone-else" })), true);
});

test("isHealthy: non-200 / non-JSON / wrong status are all not ready", () => {
  for (const [status, raw] of [
    [500, body({})],
    [200, "ok"],
    [200, "all ok"],
    [200, JSON.stringify({ status: "starting", service: SERVICE_ID })],
  ]) {
    assert.equal(isHealthy(status, raw), false, status + " + " + raw);
  }
});

test("decideStartupAction: never reuse by default; only when explicitly allowed", () => {
  assert.deepEqual(decideStartupAction({ ok: true, reason: "ok", allowReuse: false }),
    { action: "conflict", kind: "reuse-disallowed" });
  assert.deepEqual(decideStartupAction({ ok: true, reason: "ok", allowReuse: true }),
    { action: "reuse" });
});

test("decideStartupAction: start only when the port is free (refused)", () => {
  assert.deepEqual(decideStartupAction({ ok: false, reason: "refused", allowReuse: false }),
    { action: "start" });
});

test("decideStartupAction: stranger / non-200 / timeout are conflicts, never start", () => {
  for (const reason of ["identity", "status", "timeout"]) {
    const d = decideStartupAction({ ok: false, reason, allowReuse: false });
    assert.equal(d.action, "conflict", reason + " must not start");
    assert.equal(d.kind, reason);
  }
});
