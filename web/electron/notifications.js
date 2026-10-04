// 到点提醒的主进程侧（#204：从 main.js 原样搬出，行为零变更）。
//
// 为什么单独成文件：判定（该不该提醒 / 正文怎么排）已经在 reminders.js 里，但"什么时候
// 查、查到后怎么发、状态怎么存"仍缠在 main.js 的生命周期代码（窗口 / 后端 / 更新）里。
// 拆出来后 main.js 只剩接线。与 zoom.js / window_state.js 同款约定：不 require("electron")，
// electron 对象（app / BrowserWindow / Notification）与 tFor / resolvedLang 全部注入，
// ipcMain 由 registerIpc(ipcMain) 传入；http / fs / path / timers / intervalMs 可注入
// （测试用假件替换）。
//
// 搬运自 main.js L539-680（窗口就绪后与运行期内每 6 小时问一次后端 /api/reminders/due，
// 够条件就发一条系统通知，每事项每天只提醒一次），行为逐条保持：
// * **不做常驻、不建托盘**：关窗即停——由调用方在窗口 closed 时调 stopTimer()，
//   与「无后台路径」这条红线一致（本地优先的工具不该在用户以为已经退出之后还留着东西跑）。
// * 状态存 userData/reminders.json；days 与后端同口径（1–30 夹取，坏值回落默认 3）。

const {
  buildNotification,
  dueItems,
  nextState,
  shouldNotify,
  todayKey,
} = require("./reminders");

// 「提前几天开始提醒」的默认值与上限：设置页给 3/5/7，主进程按 state.days 带查询参数
const REMINDER_DAYS_DEFAULT = 3;
const REMINDER_DAYS_MAX = 30;

function createNotifications({
  app, log, tFor, resolvedLang, BrowserWindow, Notification, backendPort,
  http = require("http"), fs = require("fs"), path = require("path"),
  timers = { setInterval, clearInterval },
  intervalMs = 6 * 60 * 60 * 1000,
}) {
  let reminderState = { enabled: true, days: REMINDER_DAYS_DEFAULT, notified: {} };
  let reminderTimer = null;
  // 渲染进程上报的当前工作区（真值在它**已激活的工作区状态**，不是 localStorage 的选中记录
  // ——两者会分叉，见 preload.js）；不报就按后端默认工作区查
  let reportedWorkspace = "";

  function remindersPath() {
    return path.join(app.getPath("userData"), "reminders.json");
  }

  function loadReminders() {
    try {
      const data = JSON.parse(fs.readFileSync(remindersPath(), "utf-8"));
      const parsedDays = Number(data.days);
      reminderState = {
        enabled: data.enabled !== false,
        // 与后端 /api/reminders/due 的 days 同口径（1–30 夹取）：越界/坏值回落默认，
        // 而不是把 undefined 一路传进查询串再靠后端兜底
        days: Number.isFinite(parsedDays)
          ? Math.min(Math.max(parsedDays, 1), REMINDER_DAYS_MAX)
          : REMINDER_DAYS_DEFAULT,
        // 旧状态文件里只有 lastNotified（"哪天提醒过"）：按"每事项每天一次"的新口径
        // 它没有意义，直接丢弃——最坏情况是升级当天再报一次，比漏报轻。
        notified: data.notified && typeof data.notified === "object" ? data.notified : {},
      };
    } catch (e) {
      // 首次运行没有这个文件；文件损坏也按默认（开着、今天没提醒过）处理
      reminderState = { enabled: true, days: REMINDER_DAYS_DEFAULT, notified: {} };
    }
  }

  function saveReminders() {
    try {
      fs.mkdirSync(path.dirname(remindersPath()), { recursive: true });
      fs.writeFileSync(remindersPath(), JSON.stringify(reminderState, null, 2));
    } catch (e) {
      log(`Failed to persist reminder state: ${e.message}`);
    }
  }

  function showDueNotification(payload) {
    const t = tFor(resolvedLang());
    const { title, body } = buildNotification(t, payload);
    const notification = new Notification({ title, body });
    // 点通知就把窗口拉到前面，并把"最该看的那条"交给界面
    // （前端据此跳到追踪表并展开它——落地在 `drillToApplication` 那条既有链路）
    notification.on("click", () => {
      const win = BrowserWindow.getAllWindows()[0];
      if (win) {
        win.show();
        win.focus();
        const first = dueItems(payload)[0];
        const id = first && first.item ? first.item.id : "";
        if (id) win.webContents.send("reminder:focus", { id });
      }
    });
    notification.show();
    reminderState = nextState(reminderState, todayKey(), payload);
    saveReminders();
    log(`Reminder shown: ${body.split("\n").length} line(s)`);
  }

  function checkReminders() {
    if (!reminderState.enabled) return;
    const params = new URLSearchParams();
    if (reportedWorkspace) params.set("ws", reportedWorkspace);
    // 「提前几天」由设置项决定（后端默认 3）：它只影响"待办"这一类
    params.set("days", String(reminderState.days || REMINDER_DAYS_DEFAULT));
    const req = http.get(
      `http://127.0.0.1:${backendPort}/api/reminders/due?${params.toString()}`,
      { timeout: 4000 },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          if (res.statusCode !== 200) return;
          let payload;
          try {
            payload = JSON.parse(body);
          } catch (e) {
            return; // 坏响应既不发通知也不抛：提醒是增强，不是启动必需
          }
          if (shouldNotify(reminderState, todayKey(), payload)) showDueNotification(payload);
        });
      }
    );
    // 后端还没起来（窗口正等健康检查）是常态：静默跳过，等下一个周期
    req.on("error", () => {});
    req.on("timeout", () => req.destroy());
  }

  /** 幂等：窗口加载完成时调用；重复调用只保留一个定时器。 */
  function startReminders() {
    if (reminderTimer) return;
    loadReminders();
    checkReminders();
    reminderTimer = timers.setInterval(checkReminders, intervalMs);
  }

  function stopReminders() {
    if (!reminderTimer) return;
    timers.clearInterval(reminderTimer);
    reminderTimer = null;
  }

  /**
   * 偏好通道注册（prefs:set-workspace / prefs:set-reminders）。
   * ipcMain 由调用方传入（`registerIpc(ipcMain)`）：本模块不 require("electron")，
   * 测试里同样传替身。缺参直接抛错——通道静默缺失（preload 的 invoke 永远 reject）
   * 比启动期报错难查得多。
   */
  function registerIpc(ipcMain) {
    if (!ipcMain) {
      throw new Error("registerIpc(ipcMain) needs Electron's ipcMain: notifications.js never requires electron");
    }
    ipcMain.handle("prefs:set-workspace", (_event, ws) => {
      reportedWorkspace = String(ws || "").trim();
      log(`Workspace reported by renderer: ${reportedWorkspace || "(default)"}`);
      return { workspace: reportedWorkspace };
    });

    ipcMain.handle("prefs:set-reminders", (_event, value) => {
      // 兼容两种调用：布尔（旧调用点）与 `{ enabled?, days? }`（设置页的开关 + 提前天数）
      const patch = value && typeof value === "object" ? value : { enabled: value };
      if (typeof patch.enabled === "boolean") reminderState.enabled = patch.enabled;
      const days = Number(patch.days);
      if (Number.isFinite(days)) {
        reminderState.days = Math.max(1, Math.min(Math.round(days), REMINDER_DAYS_MAX));
      }
      saveReminders();
      // 打开或改天数后立刻看一眼，而不是等到下一个周期——按下开关/改完天数时想看到的是"现在就生效"
      if (reminderState.enabled) checkReminders();
      return { reminders: reminderState.enabled, reminderDays: reminderState.days };
    });
  }

  return {
    loadState: loadReminders,
    startTimer: startReminders,
    stopTimer: stopReminders,
    check: checkReminders,
    registerIpc,
    reminderPrefs: () => ({ enabled: reminderState.enabled, days: reminderState.days }),
    workspace: () => reportedWorkspace,
    showDueNotification,
  };
}

module.exports = { createNotifications };
