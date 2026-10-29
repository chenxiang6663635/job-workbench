// 求职工作台 · 后端身份判定（纯函数，无 electron 依赖，可被 node 直接跑）。
//
// 从 backend_process.js 抽出（2026-10-28）：身份判据与「拉起/停止进程」是两件事，
// 混在一个文件里会让两边都难改，而且这个文件已经越过 300 行规模水位。
//
// 四层身份（取自 2026-10-28 审计的区分，只有前两层在本文件里能证明）：
//   健康状态  HTTP 能响应                     ← status
//   产品身份  是 Job Workbench，不是别的服务    ← service
//   实例身份  是本次启动/被授权复用的那个实例   ← instance_id
//   数据身份  指向预期数据根                   ← 不在这里（ADR: 复用者用各自数据根）

// 产品身份标识，必须与 web/backend/main.py 的 /api/health 返回的 `service` 一致。
// 单侧改动会让桌面壳永远等不到「就绪」（表现为启动卡住）：
// 后端侧 tests/test_health_identity.py、前端侧 backend_process.test.js 各有断言。
const SERVICE_ID = "jobws";

// 本次 Electron 进程的**一次性实例标识**：spawn 时经 env 注入后端，健康检查时用来
// 确认「响应的是我拉起的那个进程」，而不只是「某个返回 ok 的服务」。
//
// 为什么产品身份不够：两个都叫 jobws 的实例可以指向**不同数据根**，service 挡不住
// 它们互相错连；而 JOBWS_DATA_DIR 只影响新启动的进程，改不了端口上已有的旧进程。
//
// 它**不是鉴权**：本地 API 的 token / Origin / Host 保护是另一项安全合同。
const INSTANCE_ID = require("crypto").randomBytes(16).toString("hex");

/**
 * 健康响应的身份判定。
 *
 * 演进史（每一步都被真实问题推着走）：
 *   ① 「正文含 ok」子串匹配 —— 连返回 ok 字样的陌生服务一起放行；
 *   ② 结构化 `status === "ok"` —— 严格了，但 2026-10-28 审计实测发现
 *      `{"status":"ok","service":"unrelated"}` 仍被接受；
 *   ③ 加 `service`（产品身份）—— 挡得住陌生服务，挡不住同一个产品的另一个实例；
 *   ④ 加可选 `expectInstance`（实例身份）—— 启动路径要求匹配，复用路径不传。
 */
function isHealthy(statusCode, body, expectInstance) {
  if (statusCode !== 200) return false;
  try {
    const parsed = JSON.parse(body);
    if (!parsed || parsed.status !== "ok") return false;
    if (parsed.service !== SERVICE_ID) return false;
    if (expectInstance && parsed.instance_id !== expectInstance) return false;
    return true;
  } catch {
    return false;
  }
}

/**
 * 启动决策（纯函数）：把「健康检查结果 + 是否允许复用」映射成动作。
 *
 * 这是「连到哪个实例」的唯一分叉点。原先写在 main.js 的
 * `if (ok) { 复用 } else { 启动 }` 里，既无法单测，又把「端口上有个身份正确的服务」
 * 直接当成「可以复用」——正是审计指出的问题。
 *
 * 返回：
 *   { action: "reuse" }                          复用现有后端（仅显式允许时）
 *   { action: "start" }                          端口空闲，启动自己的
 *   { action: "conflict", kind }                 端口被占但不是可安全复用的
 *     kind = "reuse-disallowed"  身份正确的另一个实例，但没被授权复用
 *          = "identity"          HTTP 200 但身份不符（陌生服务）
 *          = "status" / "timeout" 非 200 / 不应答
 */
function decideStartupAction({ ok, reason, allowReuse }) {
  if (ok) {
    if (allowReuse) return { action: "reuse" };
    // 默认**不**复用：端口上的实例可能指向另一个数据根，附着上去就是错连。
    return { action: "conflict", kind: "reuse-disallowed" };
  }
  if (reason === "refused") {
    // **明确的**连接被拒（ECONNREFUSED）= 端口空闲 → 启动。这是唯一会走到"启动"的分支。
    //
    // 2026-10-28 审计：`refused` 此前被所有 error 事件共用，于是 ECONNRESET / ETIMEDOUT
    // （端口上有东西但状态异常）也会走到这里。现在它们归 "error"，落到下面的冲突分支。
    return { action: "start" };
  }
  return { action: "conflict", kind: reason || "unknown" };
}

module.exports = { SERVICE_ID, INSTANCE_ID, isHealthy, decideStartupAction };
