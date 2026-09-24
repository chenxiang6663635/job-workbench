// 窗口位置尺寸记忆的纯逻辑单测：`node web/electron/window_state.test.js`（CI 也跑这一步）。
// 桌面端没有 E2E，而"窗口跑到屏幕外"这种 bug 恰恰只有真机多屏才复现——所以判定
// （夹取到某块屏、拔屏后回落、坏文件容错）全部做成纯函数，在这一层钉住。
//
// 断言消息用英文：electron 树的字符串口径是英文（check_i18n_hardcode.py 会把这里的中文串
// 当界面文案拦下）；注释仍按仓库惯例用中文。
const assert = require("assert");
const {
  MIN_WIDTH,
  MIN_HEIGHT,
  DEFAULT_WIDTH,
  DEFAULT_HEIGHT,
  clampToWorkArea,
  parseState,
  serializeState,
} = require("./window_state");

// 主屏 1920×1040（workArea：已扣掉任务栏）；副屏在**左侧**，所以坐标是负的——
// 负坐标必须被当作正常值，而不是"坏数据"。
const MAIN = { x: 0, y: 0, width: 1920, height: 1040 };
const LEFT = { x: -1280, y: 0, width: 1280, height: 1024 };

// --- 落在屏内：原样返回 --------------------------------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: 100, y: 80, width: 1200, height: 800 }, [MAIN]),
  { x: 100, y: 80, width: 1200, height: 800 },
  "a window fully inside the work area must be kept as-is"
);

// 副屏（负坐标）内的窗口同样原样保留
assert.deepStrictEqual(
  clampToWorkArea({ x: -1200, y: 0, width: 1200, height: 800 }, [MAIN, LEFT]),
  { x: -1200, y: 0, width: 1200, height: 800 },
  "negative coordinates on a left-hand display are valid, not corruption"
);

// --- 部分越界：平移进来，尺寸不变 ----------------------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: 1500, y: 900, width: 1200, height: 800 }, [MAIN]),
  { x: 720, y: 240, width: 1200, height: 800 },
  "a partially off-screen window is pushed back inside (size preserved)"
);

// --- 完全在屏幕外（显示器被拔掉）：回落到主屏居中 ------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: -3000, y: 200, width: 1200, height: 800 }, [MAIN]),
  { x: 360, y: 120, width: 1200, height: 800 },
  "a window on a detached display falls back to the centre of the primary one"
);

// --- 尺寸超过屏幕：缩到工作区大小 ----------------------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: 0, y: 0, width: 4000, height: 3000 }, [MAIN]),
  { x: 0, y: 0, width: 1920, height: 1040 },
  "an oversized window is shrunk to the work area"
);

// --- 小于最小尺寸：抬到下限（否则窗口小到没法用） ------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: 10, y: 10, width: 200, height: 100 }, [MAIN]),
  { x: 10, y: 10, width: MIN_WIDTH, height: MIN_HEIGHT },
  "a tiny window is raised to the minimum size"
);

// --- 坏数据 / 缺字段：不抛，回落到主屏居中 ------------------------------------
const centered = { x: 320, y: 80, width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT };
assert.deepStrictEqual(clampToWorkArea(null, [MAIN]), centered, "no saved state centres the default size");
assert.deepStrictEqual(clampToWorkArea({}, [MAIN]), centered, "an empty object centres the default size");
assert.deepStrictEqual(
  clampToWorkArea({ x: Number.NaN, y: 0, width: 1200, height: 800 }, [MAIN]),
  { x: 360, y: 120, width: 1200, height: 800 },
  "a NaN position falls back to centring (size kept)"
);
assert.deepStrictEqual(
  clampToWorkArea({ x: 0, y: 0, width: "wide", height: 800 }, [MAIN]),
  { x: 0, y: 0, width: DEFAULT_WIDTH, height: DEFAULT_HEIGHT },
  "a non-numeric size falls back to the default size (a valid position is still honoured)"
);

// --- 拿不到屏幕信息：不抛，也不编造坐标 ----------------------------------------
assert.deepStrictEqual(
  clampToWorkArea({ x: 10, y: 10, width: 1200, height: 800 }, []),
  { x: 0, y: 0, width: 1200, height: 800 },
  "with no displays at all it degrades to the origin instead of throwing"
);

// --- 读写状态文件：坏内容当没有，写出只留白名单字段 ----------------------------
assert.deepStrictEqual(
  parseState('{"x":1,"y":2,"width":1000,"height":700}'),
  { x: 1, y: 2, width: 1000, height: 700 }
);
assert.strictEqual(parseState("not json"), null, "garbage is treated as 'no state'");
assert.strictEqual(parseState(""), null);
assert.strictEqual(parseState(null), null);
assert.strictEqual(parseState('{"x":1,"y":2}'), null, "missing size means no usable state");
assert.strictEqual(parseState('{"x":1,"y":2,"width":1000,"height":"700"}'), null);

assert.strictEqual(
  serializeState({ x: 1.4, y: 2.6, width: 1000, height: 700, stray: "dropped" }),
  '{"x":1,"y":3,"width":1000,"height":700}',
  "only the four geometry fields are persisted, rounded to whole pixels"
);
assert.strictEqual(serializeState(null), null, "nothing to persist");

console.log("window_state.test.js: all assertions passed");
