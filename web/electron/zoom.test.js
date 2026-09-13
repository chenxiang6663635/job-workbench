// 缩放纯逻辑的无依赖单测：`node web/electron/zoom.test.js`（CI 也跑这一步）。
// 桌面端没有 E2E，主进程里能纯函数化的部分就在这一层兜住。
const assert = require("assert");
const { ZOOM_MIN, ZOOM_MAX, clampLevel, nextLevel } = require("./zoom");

// --- 夹取 ---------------------------------------------------------------------
assert.strictEqual(clampLevel(0), 0);
assert.strictEqual(clampLevel(1.5), 1.5);
assert.strictEqual(clampLevel(99), ZOOM_MAX, "越界上侧夹到上限");
assert.strictEqual(clampLevel(-99), ZOOM_MIN, "越界下侧夹到下限");
assert.strictEqual(clampLevel("abc"), 0, "非数值字符串回默认，而不是把界面缩没");
assert.strictEqual(clampLevel(undefined), 0);
assert.strictEqual(clampLevel(null), 0);
// 手工把 zoom.json 改成 {"level":"2"} 时按数值处理（宽松解析），空串视作 0
assert.strictEqual(clampLevel("1.5"), 1.5, "纯数字字符串按数值处理");
assert.strictEqual(clampLevel(""), 0, "空串是 0（Number('') === 0）");
assert.strictEqual(clampLevel("99"), ZOOM_MAX, "字符串同样受上下限约束");

// --- 按键映射 -----------------------------------------------------------------
assert.strictEqual(nextLevel(0, "=", true), 0.5);
assert.strictEqual(nextLevel(0, "+", true), 0.5, "Ctrl+Shift+= 打出的是 '+'");
assert.strictEqual(nextLevel(0, "-", true), -0.5);
assert.strictEqual(nextLevel(0, "_", true), -0.5, "Ctrl+Shift+- 打出的是 '_'");
assert.strictEqual(nextLevel(1.5, "0", true), 0, "Ctrl+0 复位");
assert.strictEqual(nextLevel(0, "=", false), null, "不带修饰键不缩放");
assert.strictEqual(nextLevel(0, "a", true), null, "其它按键不缩放");

// --- 边界：到顶/到底后按住不放，级别不再变化（也不会报错） ----------------------
assert.strictEqual(nextLevel(ZOOM_MAX, "=", true), ZOOM_MAX);
assert.strictEqual(nextLevel(ZOOM_MIN, "-", true), ZOOM_MIN);
assert.strictEqual(nextLevel(2.5, "=", true), ZOOM_MAX, "接近上限时一次按键即夹住");

// --- 往返：连续步进能回到 0，且不产生浮点尾巴 ----------------------------------
let level = 0;
for (let i = 0; i < 3; i += 1) level = nextLevel(level, "=", true);
assert.strictEqual(level, 1.5);
for (let i = 0; i < 3; i += 1) level = nextLevel(level, "-", true);
assert.strictEqual(level, 0, "三上三下必须精确回到 0（0.5 是二进制可精确表示的数）");

console.log("zoom.test.js: all assertions passed");
