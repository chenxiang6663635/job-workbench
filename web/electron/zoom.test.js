// 缩放纯逻辑的无依赖单测：`node web/electron/zoom.test.js`（CI 也跑这一步）。
// 桌面端没有 E2E，主进程里能纯函数化的部分就在这一层兜住。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把
// 这里的中文串当界面文案拦下）；注释仍按仓库惯例用中文。
const assert = require("assert");
const { ZOOM_MIN, ZOOM_MAX, clampLevel, nextLevel } = require("./zoom");

// --- 夹取 ---------------------------------------------------------------------
assert.strictEqual(clampLevel(0), 0);
assert.strictEqual(clampLevel(1.5), 1.5);
assert.strictEqual(clampLevel(99), ZOOM_MAX, "clamps above the max");
assert.strictEqual(clampLevel(-99), ZOOM_MIN, "clamps below the min");
assert.strictEqual(clampLevel("abc"), 0, "non-numeric strings fall back to default");
assert.strictEqual(clampLevel(undefined), 0);
assert.strictEqual(clampLevel(null), 0);
// 手工把 zoom.json 改成 {"level":"2"} 时按数值处理（宽松解析），空串视作 0
assert.strictEqual(clampLevel("1.5"), 1.5, "numeric strings are parsed as numbers");
assert.strictEqual(clampLevel(""), 0, "empty string counts as 0 (Number('') === 0)");
assert.strictEqual(clampLevel("99"), ZOOM_MAX, "strings are clamped too");

// --- 按键映射 -----------------------------------------------------------------
assert.strictEqual(nextLevel(0, "=", true), 0.5);
assert.strictEqual(nextLevel(0, "+", true), 0.5, "Ctrl+Shift+= produces '+'");
assert.strictEqual(nextLevel(0, "-", true), -0.5);
assert.strictEqual(nextLevel(0, "_", true), -0.5, "Ctrl+Shift+- produces '_'");
assert.strictEqual(nextLevel(1.5, "0", true), 0, "Ctrl+0 resets");
assert.strictEqual(nextLevel(0, "=", false), null, "no modifier, not a zoom key");
assert.strictEqual(nextLevel(0, "a", true), null, "other keys do not zoom");

// --- 边界：到顶/到底后按住不放，级别不再变化（也不会报错） ----------------------
assert.strictEqual(nextLevel(ZOOM_MAX, "=", true), ZOOM_MAX);
assert.strictEqual(nextLevel(ZOOM_MIN, "-", true), ZOOM_MIN);
assert.strictEqual(nextLevel(2.5, "=", true), ZOOM_MAX, "a single press near the max is clamped");

// --- 往返：连续步进能回到 0，且不产生浮点尾巴 ----------------------------------
let level = 0;
for (let i = 0; i < 3; i += 1) level = nextLevel(level, "=", true);
assert.strictEqual(level, 1.5);
for (let i = 0; i < 3; i += 1) level = nextLevel(level, "-", true);
assert.strictEqual(level, 0, "three steps up and down must land exactly on 0");

console.log("zoom.test.js: all assertions passed");
