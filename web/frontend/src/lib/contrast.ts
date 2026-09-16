// 对比度与明度计算（批 4）：与 tools/check_themes.py **同口径**——
// 主题编辑器用它做「实时对比度」提示，脚本用它做 CI 门禁；两处算法必须一致，
// 否则编辑器显示「通过」而门禁红（或反过来）。
// 输入统一为 CSS 变量里的 HSL 三元组字符串（如 "222 47% 5%"）。

export type HslTriple = [number, number, number];

/** 解析 `H S% L%`；非三元组（var(...) 别名等）返回 null。 */
export function parseHslTriple(value: string): HslTriple | null {
  const match = /^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$/.exec(value || "");
  if (!match) return null;
  return [parseFloat(match[1]), parseFloat(match[2]), parseFloat(match[3])];
}

export function hslToRgb([h, s, l]: HslTriple): [number, number, number] {
  const hh = ((h % 360) + 360) % 360 / 360;
  const ss = Math.min(100, Math.max(0, s)) / 100;
  const ll = Math.min(100, Math.max(0, l)) / 100;
  if (ss === 0) return [ll, ll, ll];
  const q = ll < 0.5 ? ll * (1 + ss) : ll + ss - ll * ss;
  const p = 2 * ll - q;
  const channel = (t: number) => {
    let tt = t;
    if (tt < 0) tt += 1;
    if (tt > 1) tt -= 1;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
  };
  return [channel(hh + 1 / 3), channel(hh), channel(hh - 1 / 3)];
}

export function relLuminance(rgb: [number, number, number]): number {
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = rgb.map(lin) as [number, number, number];
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** 两个 HSL 三元组的对比度；任一侧不可解析时返回 null。 */
export function contrastRatio(fg: string, bg: string): number | null {
  const fgTriple = parseHslTriple(fg);
  const bgTriple = parseHslTriple(bg);
  if (!fgTriple || !bgTriple) return null;
  const l1 = relLuminance(hslToRgb(fgTriple));
  const l2 = relLuminance(hslToRgb(bgTriple));
  const hi = Math.max(l1, l2);
  const lo = Math.min(l1, l2);
  return (hi + 0.05) / (lo + 0.05);
}

/** WCAG 判定（门限与 check_themes 一致：正文 4.5、大字与图形 3.0）。 */
export function wcagLevel(ratio: number, large = false): "AAA" | "AA" | "fail" {
  const aa = large ? 3 : 4.5;
  if (ratio >= (large ? 4.5 : 7)) return "AAA";
  return ratio >= aa ? "AA" : "fail";
}

/** hex（<input type="color"> 的值）→ HSL 三元组字符串。 */
export function hexToTriple(hex: string): string | null {
  const raw = (hex || "").replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(raw)) return null;
  const r = parseInt(raw.slice(0, 2), 16) / 255;
  const g = parseInt(raw.slice(2, 4), 16) / 255;
  const b = parseInt(raw.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) / 6;
    else if (max === g) h = ((b - r) / d + 2) / 6;
    else h = ((r - g) / d + 4) / 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

/** HSL 三元组 → hex（回填 color input；解析失败给中灰）。 */
export function tripleToHex(value: string): string {
  const triple = parseHslTriple(value);
  if (!triple) return "#808080";
  const [r, g, b] = hslToRgb(triple);
  const to = (c: number) => Math.round(c * 255).toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`;
}
