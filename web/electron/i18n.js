// 主进程界面文案（zh-CN / en）。
//
// 为什么主进程要自带一张表，而不是复用前端的 i18n：
// 渲染进程的语言选择存在 localStorage（`jobws_lang`），**主进程读不到**——
// 它只能按系统语言（`app.getLocale()`）挑一份。这是一个**已知取舍**，不是
// "已经打通"：用户在界面里切成英文，更新对话框仍可能跟着系统语言走中文。
// 要真打通得把选择经 IPC 送到主进程（并在渲染进程切换时同步），属后续工作；
// 这里先把"中文环境下冒出英文"这个更刺眼的问题解决掉，并把限制写在这里。
//
// 这张表也是扫描器的路径豁免对象（`tools/check_i18n_hardcode.py` 的 SKIP_DIRS）：
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
