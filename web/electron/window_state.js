// 窗口位置与尺寸记忆的**纯判定**（首发前收口批 笔 3）。
//
// 为什么单独成文件：主进程是零 E2E 覆盖区，而"记住窗口位置"最容易出的那类 bug
// （显示器拔掉之后窗口落在屏幕外、只剩任务栏底下一条缝）恰恰只在真机多屏上复现。
// 把判定做成纯函数之后，多屏、负坐标、超尺寸、坏文件这些形状都能在 CI 里断言。
//
// 与 zoom.js 同款约定：不 require("electron")，只吃数据。
//
// 坐标系：Electron 的 display.workArea（已扣掉任务栏）。副屏在主屏左边时 x 为负，
// 这是正常值——**不是**坏数据，别拿 `x > 0` 当合法性检查。

const DEFAULT_WIDTH = 1280;
const DEFAULT_HEIGHT = 880;
// 下限：窗口小于这个尺寸就没法用了（宽 960 是窄屏三档里最小的一档）
const MIN_WIDTH = 960;
const MIN_HEIGHT = 600;

function isNum(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function isArea(area) {
  return !!area && isNum(area.x) && isNum(area.y) && isNum(area.width) && isNum(area.height);
}

/** 矩形是否完全落在工作区内（边界相等算落在里面）。 */
function contains(area, rect) {
  return (
    rect.x >= area.x &&
    rect.y >= area.y &&
    rect.x + rect.width <= area.x + area.width &&
    rect.y + rect.height <= area.y + area.height
  );
}

/** 两块矩形的交集面积（无交集为 0）——用来挑"窗口大部分在哪块屏上"。 */
function overlapArea(area, rect) {
  const w = Math.min(area.x + area.width, rect.x + rect.width) - Math.max(area.x, rect.x);
  const h = Math.min(area.y + area.height, rect.y + rect.height) - Math.max(area.y, rect.y);
  return w > 0 && h > 0 ? w * h : 0;
}

function centerIn(area, size) {
  return {
    x: area.x + Math.round((area.width - size.width) / 2),
    y: area.y + Math.round((area.height - size.height) / 2),
    width: size.width,
    height: size.height,
  };
}

/**
 * 尺寸归一：坏值一律回落到默认尺寸（**两个方向要么都信、要么都不信**——只信一半会
 * 得到"宽 4000 高 800"这种更怪的窗口），再抬到下限、压到最大的那块工作区。
 */
function clampSize(bounds, areas) {
  const usable = !!bounds && isNum(bounds.width) && isNum(bounds.height);
  const rawWidth = usable ? Math.round(bounds.width) : DEFAULT_WIDTH;
  const rawHeight = usable ? Math.round(bounds.height) : DEFAULT_HEIGHT;
  const maxWidth = areas.length ? Math.max(...areas.map((a) => Math.round(a.width))) : rawWidth;
  const maxHeight = areas.length ? Math.max(...areas.map((a) => Math.round(a.height))) : rawHeight;
  return {
    width: Math.min(Math.max(rawWidth, MIN_WIDTH), maxWidth),
    height: Math.min(Math.max(rawHeight, MIN_HEIGHT), maxHeight),
  };
}

/**
 * 把保存的窗口状态收进**看得见的那块屏**。
 *
 * 三分支：完全在屏内 → 原样；与某块屏有交集 → 平移进来（挑交集最大的那块，尺寸不变）；
 * 与所有屏都无交集（显示器被拔了）→ 主屏居中。坏数据/缺字段不抛异常，同样落回居中。
 */
function clampToWorkArea(bounds, workAreas) {
  const areas = (Array.isArray(workAreas) ? workAreas : []).filter(isArea);
  const size = clampSize(bounds, areas);
  if (areas.length === 0) {
    // 一块屏都拿不到（极早期调用 / 异常环境）：给坐标 0 而不是编造一个位置
    return { x: 0, y: 0, width: size.width, height: size.height };
  }
  if (!bounds || !isNum(bounds.x) || !isNum(bounds.y)) {
    return centerIn(areas[0], size);
  }

  const rect = { x: Math.round(bounds.x), y: Math.round(bounds.y), ...size };
  for (const area of areas) {
    if (contains(area, rect)) return rect;
  }

  let best = null;
  for (const area of areas) {
    const overlap = overlapArea(area, rect);
    if (overlap > 0 && (best === null || overlap > best.overlap)) best = { area, overlap };
  }
  if (best) {
    const maxX = best.area.x + best.area.width - rect.width;
    const maxY = best.area.y + best.area.height - rect.height;
    return {
      x: Math.min(Math.max(rect.x, best.area.x), maxX),
      y: Math.min(Math.max(rect.y, best.area.y), maxY),
      width: rect.width,
      height: rect.height,
    };
  }

  return centerIn(areas[0], size);
}

/** 读状态文件：坏内容一律当"没有记录"，不让它打断启动。 */
function parseState(text) {
  if (!text) return null;
  let data;
  try {
    data = JSON.parse(text);
  } catch (e) {
    return null;
  }
  if (!data || typeof data !== "object") return null;
  if (![data.x, data.y, data.width, data.height].every(isNum)) return null;
  return {
    x: Math.round(data.x),
    y: Math.round(data.y),
    width: Math.round(data.width),
    height: Math.round(data.height),
  };
}

/** 写状态文件：只留几何四字段（别的字段一律不落盘，免得把无关状态带出去）。 */
function serializeState(bounds) {
  if (!bounds || ![bounds.x, bounds.y, bounds.width, bounds.height].every(isNum)) return null;
  return JSON.stringify({
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  });
}

module.exports = {
  DEFAULT_WIDTH,
  DEFAULT_HEIGHT,
  MIN_WIDTH,
  MIN_HEIGHT,
  clampToWorkArea,
  parseState,
  serializeState,
};
