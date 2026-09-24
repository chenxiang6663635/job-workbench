// 到点提醒的纯逻辑（首发前收口批 笔 5；2026-09-24 改「按事项去重 + 分档文案」）。
//
// 主进程做的事很薄：窗口就绪后与运行期内每几小时问一次后端 `/api/reminders/due`，够条件就
// 发一条系统通知。**该不该提醒**、**提醒几次**、**正文怎么排** 这三件事都在这里，纯函数、
// 有单测、CI 跑——桌面端没有 E2E，"今天新出现的也要报"这种约束只能在这一层钉住。
//
// 与 zoom.js / window_state.js 同款约定：不 require("electron")，只吃数据。

// 通知在 Windows 上大约三行可见，多给只会被折叠掉；计数是完整的（正文里说清"等 N 项"）
const MAX_LINES = 3;

/** 本地日期键 `YYYY-MM-DD`。刻意不用 toISOString：那是 UTC，凌晨 0–8 点会跑到前一天。 */
function todayKey(now = new Date()) {
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** 三个桶求和。缺字段/坏值一律当 0——提醒崩溃或误报都比"少一条"更糟。 */
function dueTotal(payload) {
  const counts = (payload && payload.counts) || {};
  const read = (name) => (Number.isFinite(counts[name]) ? counts[name] : 0);
  return read("overdue") + read("todos") + read("talks");
}

/**
 * 三桶压成"要显示的条目"（顺序：先过期的，再待办，最后宣讲会）。
 *
 * 每条的 `key` 用于**按事项去重**（`<bucket>:<id>`）。旧口径是"一天只提醒一次"
 * （状态里只记哪天提醒过），于是今天提醒过之后、**今天新出现的**截止项就再也
 * 不报了——而那恰恰是最该报的一类。
 */
function dueItems(payload) {
  const items = [];
  const push = (bucket, item) => {
    // 先在语句里取好 id：模板串里出现中文会被 i18n 硬编码检查拦下，
    // 而那段检查的片段格式不接受 `||`（竖线是分隔符）——所以不写成一整串
    const id = item.id || item.公司 || "";
    items.push({
      key: `${bucket}:${id}`,
      bucket,
      item,
      daysLeft: Number(item.daysLeft) || 0,
    });
  };
  for (const item of (payload && payload.overdue) || []) push("overdue", item);
  for (const item of (payload && payload.todos) || []) push("todos", item);
  for (const item of (payload && payload.talks) || []) push("talks", item);
  return items;
}

/** 该不该发：**还有没报过的条目**就发（每事项每天一次；今天新出现的也算没报过）。 */
function shouldNotify(state, today, payload) {
  if (dueTotal(payload) === 0) return false;
  const notified = (state && state.notified) || {};
  return dueItems(payload).some((entry) => notified[entry.key] !== today);
}

/**
 * 通知正文：**先说过期的**（已经损失了的），再说待办（今天到期 / 还剩几天），
 * 最后宣讲会。每条都给"公司 + 岗位"，因为通知面板里只能看到一两行——用户要能
 * 一眼判断"这跟我现在做的事有没有关系"。超出的收成一句"等 N 项"。
 */
function buildNotification(t, payload) {
  const lines = [];
  for (const { bucket, item, daysLeft } of dueItems(payload)) {
    if (bucket === "overdue") {
      lines.push(t("reminderOverdue", {
        company: item.公司 || "",
        position: item.岗位 || "",
        date: item.date || item.截止日期 || "",
        days: Math.abs(daysLeft),
      }));
    } else if (bucket === "todos") {
      // 今天到期用 reminderTodo/Note（不带天数），提前几天用 reminderSoon——
      // "还剩 3 天"与"今天到期"是两种紧迫度，正文里必须能一眼分开
      const due = daysLeft <= 0;
      lines.push(t(
        due ? (item.说明 ? "reminderTodoNote" : "reminderTodo") : "reminderSoon",
        {
          company: item.公司 || "",
          position: item.岗位 || "",
          date: item.date || "",
          note: item.说明 || "",
          days: daysLeft,
        }
      ));
    } else {
      lines.push(t("reminderTalk", { company: item.公司 || "", time: item.时间 || "" }));
    }
  }
  const total = dueTotal(payload);
  const shown = lines.slice(0, MAX_LINES);
  if (total > shown.length) {
    shown.push(t("reminderMore", { count: total - shown.length }));
  }
  return { title: t("reminderTitle"), body: shown.join("\n") };
}

/**
 * 提醒过之后的新状态：记下**这次报过哪些条目**（每事项每天只报一次）。
 *
 * 只保留今天的键——状态文件长期存在，不清理会随年月无限增长。
 */
function nextState(state, today, payload) {
  const notified = {};
  for (const { key } of dueItems(payload || {})) {
    notified[key] = today;
  }
  return { notified, enabled: !state || state.enabled !== false };
}

module.exports = {
  MAX_LINES,
  todayKey,
  dueTotal,
  dueItems,
  shouldNotify,
  buildNotification,
  nextState,
};
