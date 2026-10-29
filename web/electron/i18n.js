// 主进程界面文案（zh-CN / en）。
//
// 为什么主进程要自带一张表，而不是复用前端的 i18n：
// 这张表是**回退链的一环**——渲染进程的语言选择存在 localStorage（`jobws_lang`），
// 主进程读不到；现在由渲染进程经 IPC 主动上报（`prefs:set-lang` →
// main.js 的 `currentLang`，见 preload 的 `setLang`），**上报前**按系统语言
// （`app.getLocale()`）挑一份。所以本表服务于「首帧 / 尚未上报」的窗口标题与
// 更新对话框，两边用词需保持同步。
//
// 这张表也是扫描器的路径豁免对象（`tools/jobws.py lint i18n` 的 SKIP_DIRS）：
// 语言包本来就是这些字面量的家——与前端 `i18n/locales/` 同理。别把业务文案写到
// 别处再指望豁免。
//
// 占位符用 `{name}`，由 format() 替换（不用模板函数，保持表是纯数据）。

const TABLES = {
  en: {
    windowTitle: "Job Workbench",
    updateAvailableTitle: "Update available",
    updateAvailableMessage: "Job Workbench {version} is available",
    updateAvailableDetail:
      "You will be asked whether to restart after the download completes. " +
      "Downloading now will not interrupt what you are doing.",
    updateAvailableDownload: "Download update",
    updateAvailableLater: "Later",
    updateReadyTitle: "Update ready",
    updateReadyMessage: "Job Workbench {version} has been downloaded",
    updateReadyDetail:
      "Restarting quits the backend process first, then installs the new version.",
    updateReadyRestart: "Restart and install",
    updateReadyInstallOnQuit: "Install on quit",
    updateFailedTitle: "Update check failed",
    updateFailedMessage: "Could not check for updates. The app keeps working; try again later.",
    backendStartFailedTitle: "Backend did not start",
    backendStartFailedMessage: "The backend exited right after launch (code {code}).",
    backendStartFailedDetail:
      "Usual causes: missing Python dependencies, the port already in use, or a data folder that cannot be written. See the app log for the backend output. Step-by-step checks: docs/usage-guide (FAQ).",
    backendDiedTitle: "Backend stopped",
    backendDiedMessage: "The backend exited while running (code {code}); the UI no longer works.",
    backendDiedDetail: "Please restart the app. If it keeps happening, click Copy diagnostics below and send what it gives you; step-by-step checks: docs/usage-guide (FAQ).",
    copyDiag: "Copy diagnostics",
    // 2026-10-29 审计 3.3：原文是「paste it into your bug report」——那是**承诺**诊断
    // 可安全公开，但 redactHome 只脱敏主目录；日志尾部仍可能含邮箱、公司名、JD 路径。
    // 文案改成「先检查再贴」，注释可以慢点改，这句是用户实际照着做的指令。
    diagCopied: "Diagnostics copied to the clipboard. Review it and remove anything sensitive "
      + "(email addresses, file paths, company names) before pasting into a public bug report.",
    backendTimeoutTitle: "Backend startup timed out",
    backendTimeoutMessage: "The backend was not ready after {seconds} seconds:",
    backendMissingPythonTitle: "Backend not found",
    backendMissingPythonMessage:
      "Neither the bundled backend nor a usable Python was found. Install Python 3.12+ with FastAPI and uvicorn, or set JOBWS_PYTHON to an interpreter that has them. Setup steps: docs/usage-guide, section 1.",
    reminderTitle: "Job Workbench · due today",
    reminderOverdue: "{company} {position} — deadline passed {days}d ago ({date})",
    reminderTodo: "{company} {position} · {date}",
    reminderTodoNote: "{company} {position} · {date} · {note}",
    reminderSoon: "{company} {position} · {days}d left · {date}",
    reminderTalk: "{company} · talk at {time}",
    reminderMore: "{count} more",
    // 启动阶段的两个阻断提示（2026-10-28 审计 §七 第 2 条：此前散落在 main.js /
    // backend_process.js 里的字面量，中文用户看到的是英文）
    portConflictTitle: "Cannot start: backend port is in use",
    portConflictReuseDetail:
      "Another Job Workbench backend is already listening on 127.0.0.1:8765.\n\n"
      + "It may point to a different data root. Attaching would show or write the "
      + "wrong workspace, so this window will not open.\n\n"
      + "• To use that instance: open it directly (do not start a second one).\n"
      + "• To reuse it from this shell anyway: set JOBWS_ALLOW_REUSE=1.\n"
      + "• To start fresh: quit that instance first.",
    portConflictOtherDetail:
      "The port 127.0.0.1:8765 is held by something that is not a healthy "
      + "Job Workbench backend ({kind}).\n\n"
      + "This app will not attach to it, and will not kill it.\n\n"
      + "• Find and close whatever holds the port, then start again.",
    backendTimeoutHintIdentity:
      "The port is answering, but not as the backend this window started "
      + "— most likely another Job Workbench instance owns it.\n"
      + "Waiting longer will not help: quit that instance (or set "
      + "JOBWS_ALLOW_REUSE=1 to attach to it deliberately).",
  },
  "zh-CN": {
    windowTitle: "求职工作台",
    updateAvailableTitle: "有可用更新",
    updateAvailableMessage: "求职工作台 {version} 可以更新",
    updateAvailableDetail:
      "下载完成后会先问你是否重启；下载本身不会打断你正在做的事。",
    updateAvailableDownload: "下载更新",
    updateAvailableLater: "稍后",
    updateReadyTitle: "更新已就绪",
    updateReadyMessage: "求职工作台 {version} 已下载完成",
    updateReadyDetail: "重启会先结束后端进程，再安装新版本。",
    updateReadyRestart: "重启并安装",
    updateReadyInstallOnQuit: "退出时安装",
    updateFailedTitle: "更新检查失败",
    updateFailedMessage: "没能检查到更新。应用可继续使用，可稍后再试。",
    backendStartFailedTitle: "后端未能启动",
    backendStartFailedMessage: "后端进程启动后立即退出（退出码 {code}）。",
    backendStartFailedDetail:
      "常见原因：Python 依赖缺失、端口已被占用、数据目录不可写。后端完整输出见应用日志。逐项排查见仓库 docs/usage-guide 的「常见问题」章。",
    backendDiedTitle: "后端已停止",
    backendDiedMessage: "后端在运行中退出（退出码 {code}），界面上的操作将不再生效。",
    backendDiedDetail: "请重启应用；若反复出现，点下方「复制诊断信息」把日志尾部复制出来一起反馈。重启仍失败时看 docs/usage-guide 的「常见问题」章。",
    copyDiag: "复制诊断信息",
    // 同英文侧（2026-10-29 审计 3.3）：只脱敏主目录，别承诺「可直接贴」
    diagCopied: "诊断信息已复制到剪贴板。提交公开反馈前请先检查并删除敏感内容"
      + "（邮箱、文件路径、公司名）。",
    backendTimeoutTitle: "后端启动超时",
    backendTimeoutMessage: "等了 {seconds} 秒后端仍未就绪：",
    backendMissingPythonTitle: "找不到后端",
    backendMissingPythonMessage:
      "既没有随包的后端程序，也没找到可用的 Python。请安装 Python 3.12+ 与 FastAPI / uvicorn，或用 JOBWS_PYTHON 指向具备这些依赖的解释器。安装步骤见 docs/usage-guide 的环境准备章。",
    reminderTitle: "求职工作台 · 今日提醒",
    reminderOverdue: "{company} {position}：已过截止 {days} 天（{date}）",
    reminderTodo: "{company} {position} · {date}",
    reminderTodoNote: "{company} {position} · {date} · {note}",
    reminderSoon: "{company} {position}：还剩 {days} 天 · {date}",
    reminderTalk: "{company} · 宣讲会 {time}",
    reminderMore: "等 {count} 项",
    // 启动阶段的两个阻断提示（2026-10-28 审计 §七 第 2 条：此前是硬编码英文）
    portConflictTitle: "无法启动：后端端口被占用",
    portConflictReuseDetail:
      "127.0.0.1:8765 上已经有一个求职工作台后端在监听。\n\n"
      + "它可能指向另一个数据根。附着上去会看到或写进错误的工作区，所以这个窗口不会打开。\n\n"
      + "• 想用那个实例：直接打开它（不要再起第二个）。\n"
      + "• 确实要从这里复用它：设 JOBWS_ALLOW_REUSE=1。\n"
      + "• 想从头启动：先退出那个实例。",
    portConflictOtherDetail:
      "127.0.0.1:8765 被一个「不是」健康求职工作台后端的东西占着（{kind}）。\n\n"
      + "本程序不会附着到它，也不会结束它。\n\n"
      + "• 找到并关掉占着端口的那个程序，然后重新启动。",
    backendTimeoutHintIdentity:
      "端口在应答，但「不是」本窗口启动的那个后端——很可能是另一个求职工作台实例占着它。\n"
      + "继续等待不会好转：先退出那个实例（或设 JOBWS_ALLOW_REUSE=1 明确附着到它）。",
  },
};

/** 系统语言 → 表名。zh* 一律按 zh-CN（zh-TW 等变体暂不细分，与前端口径一致）。 */
function pickLang(locale) {
  return String(locale || "").toLowerCase().startsWith("zh") ? "zh-CN" : "en";
}

function format(template, params) {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : whole
  );
}

/**
 * 取一个绑定到某语言的 t(key, params)。
 *
 * 缺失 key 时回落英文表、再退化为 key 名本身——**不抛异常**：主进程抛出去会
 * 直接打断更新对话框这条链路，而"少一句译文"远没有"更新流程挂了"严重。
 */
function tFor(locale) {
  const lang = pickLang(locale);
  return function t(key, params) {
    let template = TABLES[lang][key];
    if (template === undefined) template = TABLES.en[key];
    if (template === undefined) return key;
    return format(template, params);
  };
}

module.exports = { TABLES, pickLang, tFor };
