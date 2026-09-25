// 诊断文本拼装的无依赖单测：`node web/electron/diagnostics.test.js`（CI 也跑这一步）。
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里
// 的中文串当界面文案拦下）；注释仍按仓库惯例用中文。
const assert = require("assert");
const { buildDiagnostics, redactHome } = require("./diagnostics");

// --- 脱敏：主目录出现即替换成 <home>（诊断文本要能安全贴进公开 issue） -------------
assert.strictEqual(
  redactHome("C:\\Users\\cx\\AppData\\Roaming\\job-workbench", "C:\\Users\\cx"),
  "<home>\\AppData\\Roaming\\job-workbench"
);
assert.strictEqual(redactHome("twice C:\\Users\\cx\\a and C:\\Users\\cx\\b", "C:\\Users\\cx"),
  "twice <home>\\a and <home>\\b", "every occurrence must be redacted");
assert.strictEqual(redactHome("no home here", ""), "no home here",
  "empty home must pass through unchanged (never guess)");
assert.strictEqual(redactHome("plain text", undefined), "plain text");

// --- 拼装：版本 / 运行时 / 平台 / 日志路径 / 尾部日志，一段可粘贴的文本 ------------
const text = buildDiagnostics({
  version: "26.9.0",
  electron: "44.0.0",
  node: "22.0.0",
  platform: "win32",
  arch: "x64",
  logPath: "C:\\Users\\cx\\AppData\\Roaming\\job-workbench\\main.log",
  tail: "[job-workbench] 2026-09-25T00:00:00Z Backend ready\n[job-workbench] [backend-err] boom\n",
  home: "C:\\Users\\cx",
});

assert.ok(text.includes("job-workbench 26.9.0"), "version line");
assert.ok(text.includes("Electron 44.0.0 / Node 22.0.0"), "runtime line");
assert.ok(text.includes("Platform win32 x64"), "platform line");
assert.ok(text.includes("--- main.log (tail) ---"), "tail separator");
assert.ok(text.includes("[backend-err] boom"), "backend stderr must be present");
assert.ok(!text.includes("Users\\cx"), "home path must be redacted:\n" + text);
assert.ok(text.includes("<home>\\AppData"), "redaction marker present");
assert.ok(!text.endsWith("\n\n"), "tail trailing newline should be trimmed");

// --- 尾部缺失（读日志失败）时不抛错：拼装仍可用 -----------------------------------
const bare = buildDiagnostics({
  version: "26.9.0", electron: "44", node: "22",
  platform: "win32", arch: "x64", logPath: "x", home: "",
});
assert.ok(bare.includes("--- main.log (tail) ---"));

console.log("diagnostics.test.js: all assertions passed");
