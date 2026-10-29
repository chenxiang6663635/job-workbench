// 启动阶段的用户可见文案：端口冲突对话框、启动超时里的「另一个实例占着端口」提示。
//
// 为什么单独成模块（2026-10-28 审计 §七 第 2 条）：这两处此前是**硬编码英文**，中文
// 用户看到英文；而 `check_i18n_hardcode` 只查中文，抓不到「英文没进语言表」。放在
// `main.js` / `backend_process.js` 里也不行——两者都 require("electron")，node 测不了。
// 这里只做「语言表 → 文案」的拼装；文案本身留在 `i18n.js`（扫描器的豁免对象），
// 与 `backend_identity` / `url_guard` 一样是零依赖的纯函数模块。

function conflictText(kind, t) {
  const title = t("portConflictTitle");
  const detail = kind === "reuse-disallowed"
    ? t("portConflictReuseDetail")
    : t("portConflictOtherDetail", { kind });
  return { title, detail };
}

function timeoutHint(reason, t) {
  return reason === "identity" ? t("backendTimeoutHintIdentity") : "";
}

module.exports = { conflictText, timeoutHint };
