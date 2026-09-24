// 到点提醒的纯逻辑（首发前收口批 笔 5）。
//
// 主进程做的事很薄：窗口就绪后与运行期内每几小时问一次后端 `/api/reminders/due`，够条件就
// 发一条系统通知。**该不该提醒**、**提醒几次**、**正文怎么排** 这三件事都在这里，纯函数、
// 有单测、CI 跑——桌面端没有 E2E，"一天只提醒一次"这种约束只能在这一层钉住。
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

/** 该不该发：有到点的事，且今天还没提醒过（状态里只记"哪天提醒过"）。 */
function shouldNotify(state, today, payload) {
  if (dueTotal(payload) === 0) return false;
  return !(state && state.lastNotified === today);
}

/**
 * 通知正文：**先说过期的**（已经损失了的），再说近七天的待办，最后宣讲会。
 *
 * 每条都给"公司 + 岗位 + 日期"，因为通知面板里只能看到一两行——用户要能一眼判断
 * "这跟我现在做的事有没有关系"。超出的收成一句"等 N 项"。
 */
function buildNotification(t, payload) {
  const lines = [];
  for (const item of payload.overdue || []) {
    lines.push(t("reminderOverdue", {
      company: item.公司 || "",
      position: item.岗位 || "",
      date: item.截止日期 || "",
    }));
  }
  for (const item of payload.todos || []) {
    // 有"下次动作"的才带说明：否则正文里会多出一个空的间隔符
    lines.push(t(item.说明 ? "reminderTodoNote" : "reminderTodo", {
      company: item.公司 || "",
      position: item.岗位 || "",
      date: item.date || "",
      note: item.说明 || "",
    }));
  }
  for (const item of payload.talks || []) {
    lines.push(t("reminderTalk", {
      company: item.公司 || "",
      time: item.时间 || "",
    }));
  }
  const total = dueTotal(payload);
  const shown = lines.slice(0, MAX_LINES);
  if (total > shown.length) {
    shown.push(t("reminderMore", { count: total - shown.length }));
  }
  return { title: t("reminderTitle"), body: shown.join("\n") };
}

/** 提醒过之后的新状态（保留开关键——状态文件是同一份）。 */
function nextState(state, today) {
  return {
    lastNotified: today,
    enabled: !state || state.enabled !== false,
  };
}

module.exports = { MAX_LINES, todayKey, dueTotal, shouldNotify, buildNotification, nextState };
