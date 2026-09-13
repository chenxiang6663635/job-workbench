// 界面缩放的纯逻辑（与 Electron 无关，可被 node 直接跑，见 zoom.test.js）。
//
// 为什么把这一小段拆出来：上下限夹取、按键映射（Shift 变体与小键盘）、
// ±0.5 步进不越界——全都能用纯函数表达。留在主进程里就只能靠手点验证，
// 而「手点」恰恰是最容易被跳过的一步；这里给出的 pytest 之外的第二种
// 机检入口，代价只有几十行。
const ZOOM_MIN = -3;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.5;

/** 夹取到合法范围。非数值输入（NaN / undefined / null / 非纯数字字符串）回 0——
    不能把界面缩没；纯数字字符串（zoom.json 被手工改成 `"2"`）按数值处理，宽松
    解析比拒绝更稳。行为由 zoom.test.js 钉住。 */
function clampLevel(level) {
  const n = Number(level);
  if (!Number.isFinite(n)) return 0;
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, n));
}

/** 按键 → 目标级别；返回 null 表示「这次按键不是缩放」，调用方不该拦它。 */
function nextLevel(current, key, withModifier) {
  if (!withModifier) return null;
  let next = null;
  if (key === "=" || key === "+") {
    next = current + ZOOM_STEP;
  } else if (key === "-" || key === "_") {
    next = current - ZOOM_STEP;
  } else if (key === "0") {
    next = 0;
  }
  if (next === null) return null;
  return clampLevel(next);
}

module.exports = { ZOOM_MIN, ZOOM_MAX, ZOOM_STEP, clampLevel, nextLevel };
