// 诊断信息拼装（纯函数：无 Electron、无 IO、无全局状态——可直接 `node` 跑单测）。
//
// 为什么单独成模块：调研过的成熟做法指向同一件事——故障当下要给用户一个把有效
// 信息交出来的出口（VS Code 的 `Developer: Open Logs Folder`、Slack 故障弹窗里的
// Download Logs、Obsidian 生态的「复制诊断报告」命令）。内容拼装与脱敏是纯逻辑，
// 抽出来才有测试；main.js 保持「调度」角色（弹窗、读文件、写剪贴板）。
//
// 隐私边界：本函数只拼字符串。写剪贴板 / 弹提示由调用方做——本地生成、永不上传。

/**
 * 拼一段可粘贴的诊断文本。
 * @param {object} ctx
 * @param {string} ctx.version   应用版本（`app.getVersion()`）
 * @param {string} ctx.electron  Electron 版本
 * @param {string} ctx.node      Node 版本
 * @param {string} ctx.platform  `process.platform`
 * @param {string} ctx.arch      `process.arch`
 * @param {string} ctx.logPath   日志文件绝对路径
 * @param {string} ctx.tail      日志尾部原文（调用方读好传入）
 * @param {string} [ctx.home]    用户主目录——文本里出现即脱敏成 `<home>`
 */
function buildDiagnostics(ctx) {
  const head = [
    `job-workbench ${ctx.version}`,
    `Electron ${ctx.electron} / Node ${ctx.node}`,
    `Platform ${ctx.platform} ${ctx.arch}`,
    `Log file: ${ctx.logPath}`,
  ];
  const body = ["", "--- main.log (tail) ---", String(ctx.tail || "").trimEnd()];
  return redactHome(head.concat(body).join("\n"), ctx.home);
}

/**
 * 主目录（含本机用户名）出现在日志路径与日志行里——诊断文本要能安全贴进公开 issue。
 * 用 `split/join` 而不是正则：Windows 路径里的反斜杠在正则里要再造一层转义。
 */
function redactHome(text, home) {
  if (!home) return text;
  return text.split(home).join("<home>");
}

module.exports = { buildDiagnostics, redactHome };
