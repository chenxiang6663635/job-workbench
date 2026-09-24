// 到点提醒的纯逻辑单测：`node web/electron/reminders.test.js`（CI 也跑这一步）。
// 桌面端没有 E2E，"每事项每天只报一次"与"今天新出现的也要报"只能在这一层钉住。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const assert = require("assert");
const {
  todayKey,
  dueTotal,
  dueItems,
  shouldNotify,
  buildNotification,
  nextState,
} = require("./reminders");

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

// --- dueItems：顺序（先过期 → 待办 → 宣讲会）+ 去重键 + daysLeft 兜底 ---------------
const ordered = dueItems({
  overdue: [{ id: "A001", 公司: "甲公司", daysLeft: -4 }],
  todos: [{ id: "A002", 公司: "乙公司", daysLeft: 3 }],
  talks: [{ id: "T001", 公司: "丙公司" }],
});
assert.deepStrictEqual(
  ordered.map((entry) => entry.key),
  ["overdue:A001", "todos:A002", "talks:T001"],
  "overdue first, then todos, then talks"
);
assert.strictEqual(ordered[0].daysLeft, -4);
assert.strictEqual(ordered[2].daysLeft, 0, "a talk without daysLeft is treated as today");
assert.deepStrictEqual(dueItems(null), []);

// --- shouldNotify：**每事项每天一次**（今天新出现的也要报） -------------------------
const payload = {
  counts: { todos: 1, talks: 0, overdue: 0 },
  todos: [{ id: "A001", 公司: "A" }],
};
assert.strictEqual(shouldNotify({ notified: {} }, "2026-09-23", payload), true);
assert.strictEqual(
  shouldNotify({ notified: { "todos:A001": "2026-09-23" } }, "2026-09-23", payload),
  false,
  "an item already reported today stays quiet"
);
assert.strictEqual(
  shouldNotify({ notified: { "todos:A001": "2026-09-22" } }, "2026-09-23", payload),
  true,
  "a new day notifies again"
);
assert.strictEqual(
  shouldNotify({ notified: { "todos:A001": "2026-09-23" } }, "2026-09-23", {
    counts: { todos: 2, talks: 0, overdue: 0 },
    todos: [{ id: "A001", 公司: "A" }, { id: "A002", 公司: "B" }],
  }),
  true,
  "an item that appeared later today still notifies"
);
assert.strictEqual(shouldNotify({ notified: {} }, "2026-09-23", { counts: {} }), false, "nothing due, no notification");
assert.strictEqual(shouldNotify(null, "2026-09-23", payload), true, "no state file yet");

// --- buildNotification：先说过期的，再说剩余天数，最后宣讲会；多的收成"等 N 项" -----
const t = (key, params) => {
  if (!params) return key;
  const rendered = Object.keys(params).sort().map((name) => `${name}=${params[name]}`).join("|");
  return `${key}|${rendered}`;
};

const single = buildNotification(t, {
  workspace: "personal",
  counts: { todos: 1, talks: 0, overdue: 0 },
  todos: [{ id: "A001", 公司: "A", 岗位: "P", date: "2026-09-25", 说明: "发跟进邮件", daysLeft: 2 }],
  talks: [],
  overdue: [],
});
assert.strictEqual(single.title, "reminderTitle");
assert.ok(single.body.includes("A"), single.body);
assert.ok(single.body.includes("reminderSoon"), "a future item says how many days are left: " + single.body);
assert.ok(single.body.includes("days=2"), single.body);

// 今天到期（daysLeft=0）走 reminderTodo/Note：与"还剩 N 天"在正文里能一眼分开
const todayItem = buildNotification(t, {
  counts: { todos: 1, talks: 0, overdue: 0 },
  todos: [{ id: "A001", 公司: "A", 岗位: "P", date: "2026-09-23", 说明: "", daysLeft: 0 }],
});
assert.ok(todayItem.body.includes("reminderTodo|"), todayItem.body);

const many = buildNotification(t, {
  workspace: "personal",
  counts: { todos: 5, talks: 2, overdue: 1 },
  overdue: [{ id: "A001", 公司: "甲公司", 岗位: "后端", date: "2026-09-20", daysLeft: -3 }],
  todos: [
    { id: "A002", 公司: "乙公司", 岗位: "算法", date: "2026-09-24", 说明: "", daysLeft: 0 },
    { id: "A003", 公司: "丙公司", 岗位: "前端", date: "2026-09-25", 说明: "", daysLeft: 3 },
  ],
  talks: [{ id: "T001", 公司: "丁公司", 时间: "2026-09-26 14:00" }],
});
const lines = many.body.split("\n");
assert.ok(lines.length >= 2, "body lists the most urgent items first: " + many.body);
assert.ok(many.body.startsWith(lines[0]) && lines[0].includes("甲公司"), "overdue comes first: " + many.body);
assert.ok(many.body.includes("days=3"), "the overdue line says how long ago: " + many.body);
assert.ok(many.body.includes("reminderMore"), "leftovers are summarised as a count: " + many.body);
assert.ok(many.body.includes("count=5"), "the count is what is left after the listed lines: " + many.body);

// --- nextState：记下"这次报过哪些条目"，且只留今天的键（状态文件不能无限增长） ------
assert.deepStrictEqual(nextState({ enabled: true }, "2026-09-23", payload), {
  notified: { "todos:A001": "2026-09-23" },
  enabled: true,
});
assert.deepStrictEqual(nextState(null, "2026-09-23", payload), {
  notified: { "todos:A001": "2026-09-23" },
  enabled: true,
});
assert.deepStrictEqual(
  nextState({ notified: { "todos:A999": "2026-09-22" }, enabled: true }, "2026-09-23", payload),
  { notified: { "todos:A001": "2026-09-23" }, enabled: true },
  "stale keys from previous days are dropped"
);

// --- nextState 保留持久化字段 days：否则第一条通知当天「提前几天」就被重置回默认 --
assert.deepStrictEqual(
  nextState({ enabled: true, days: 5 }, "2026-09-23", payload),
  { notified: { "todos:A001": "2026-09-23" }, enabled: true, days: 5 },
  "days survives the state transition"
);
assert.strictEqual(
  nextState({ enabled: true, days: 7 }, "2026-09-24", payload).days, 7,
  "days keeps its value across days too"
);

console.log("reminders.test.js: all assertions passed");
