// 到点提醒的纯逻辑单测：`node web/electron/reminders.test.js`（CI 也跑这一步）。
// 桌面端没有 E2E，"一天只提醒一次"这种事只能在这一层钉住。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const assert = require("assert");
const { todayKey, dueTotal, shouldNotify, buildNotification, nextState } = require("./reminders");

// --- todayKey：本地日期（不是 UTC——凌晨 0–8 点用 UTC 会跑到前一天） --------------
assert.strictEqual(todayKey(new Date(2026, 8, 23, 23, 59)), "2026-09-23");
assert.strictEqual(todayKey(new Date(2026, 0, 5, 0, 1)), "2026-01-05", "early morning stays on the same local day");
assert.strictEqual(todayKey(new Date(2026, 11, 31, 8, 0)), "2026-12-31");

// --- dueTotal：三个桶求和；缺字段/坏值当 0（提醒多一条比崩溃好，少一条比误报好）----
assert.strictEqual(dueTotal({ counts: { todos: 2, talks: 1, overdue: 3 } }), 6);
assert.strictEqual(dueTotal({ counts: { todos: 0, talks: 0, overdue: 0 } }), 0);
assert.strictEqual(dueTotal({}), 0, "missing counts means nothing due");
assert.strictEqual(dueTotal(null), 0);
assert.strictEqual(dueTotal({ counts: { todos: "many" } }), 0, "garbage counts are not trusted");

// --- shouldNotify：有内容 且 今天还没提醒过 ------------------------------------------
const payload = { counts: { todos: 1, talks: 0, overdue: 0 } };
assert.strictEqual(shouldNotify({ lastNotified: "" }, "2026-09-23", payload), true);
assert.strictEqual(shouldNotify({ lastNotified: "2026-09-22" }, "2026-09-23", payload), true, "a new day notifies again");
assert.strictEqual(shouldNotify({ lastNotified: "2026-09-23" }, "2026-09-23", payload), false, "once per day");
assert.strictEqual(shouldNotify({ lastNotified: "" }, "2026-09-23", { counts: {} }), false, "nothing due, no notification");
assert.strictEqual(shouldNotify(null, "2026-09-23", payload), true, "no state file yet");

// --- buildNotification：先说过期的，再今天/近七天，最后宣讲会；多的收成"等 N 项" -------
const t = (key, params) => {
  if (!params) return key;
  const rendered = Object.keys(params).sort().map((name) => `${name}=${params[name]}`).join("|");
  return `${key}|${rendered}`;
};

const single = buildNotification(t, {
  workspace: "personal",
  counts: { todos: 1, talks: 0, overdue: 0 },
  todos: [{ 公司: "云帆智算", 岗位: "数据平台", date: "2026-09-25", 说明: "发跟进邮件" }],
  talks: [],
  overdue: [],
});
assert.strictEqual(single.title, "reminderTitle");
assert.ok(single.body.includes("云帆智算"), single.body);

const many = buildNotification(t, {
  workspace: "personal",
  counts: { todos: 5, talks: 2, overdue: 1 },
  overdue: [{ 公司: "甲公司", 岗位: "后端", 截止日期: "2026-09-20" }],
  todos: [
    { 公司: "乙公司", 岗位: "算法", date: "2026-09-24", 说明: "" },
    { 公司: "丙公司", 岗位: "前端", date: "2026-09-25", 说明: "" },
  ],
  talks: [{ 公司: "丁公司", 时间: "2026-09-26 14:00" }],
});
const lines = many.body.split("\n");
assert.ok(lines.length >= 2, "body lists the most urgent items first: " + many.body);
assert.ok(many.body.startsWith(lines[0]) && lines[0].includes("甲公司"), "overdue comes first: " + many.body);
assert.ok(many.body.includes("reminderMore"), "leftovers are summarised as a count: " + many.body);
assert.ok(many.body.includes("count=5"), "the count is what is left after the listed lines: " + many.body);

// --- nextState：只记"哪天提醒过" -----------------------------------------------------
assert.deepStrictEqual(nextState({ lastNotified: "2026-09-22", enabled: true }, "2026-09-23"), {
  lastNotified: "2026-09-23",
  enabled: true,
});
assert.deepStrictEqual(nextState(null, "2026-09-23"), { lastNotified: "2026-09-23", enabled: true });

console.log("reminders.test.js: all assertions passed");
