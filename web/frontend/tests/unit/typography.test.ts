import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * 中文排版两条下限的**声明级回归网**（首发前收口批 笔 6）。
 *
 * 外部调研给了两条可直接核对、且只需改取值就能满足的规矩：暗色界面避免纯黑与纯白
 * （halation 光晕），小字号避免低于 400 的字重（中文笔画在小字号下会糊）。
 *
 * 本轮**核对结果是两条都合规**（十套主题的暗色底最低 5%、暗色正文最高 96%，没有任何
 * `#000` / `#fff` / `0 0% 0%` / `0 0% 100%`；全仓也没有 `font-light|thin|extralight`）。
 * 所以这一笔不为了改而改，只把结论固化成断言——下一次有人把某套主题的底色压到 0%
 * 或加一处 `font-light`，这里会先红。
 *
 * 判定范围刻意写清：
 * - **表面**（background / card / popover）只在**暗色**主题上判（亮色主题的纯白卡片是
 *   刻意的，改它会牵动 `check_themes` 的明度阶梯门禁，收益不抵风险）；
 * - **正文**（foreground）两种模式都判：亮色不取纯黑、暗色不取纯白。
 */
const here = dirname(fileURLToPath(import.meta.url));
const THEMES_DIR = resolve(here, "../../src/themes");
const SRC_DIR = resolve(here, "../../src");

const SURFACES = ["--background", "--card", "--popover"];

function tokens(css: string): Record<string, { h: number; s: number; l: number }> {
  const out: Record<string, { h: number; s: number; l: number }> = {};
  const re = /(--[a-z-]+):\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s*;/g;
  let match;
  while ((match = re.exec(css)) !== null) {
    out[match[1]] = { h: Number(match[2]), s: Number(match[3]), l: Number(match[4]) };
  }
  return out;
}

function cssFiles(root: string, depth = 2): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const full = resolve(root, entry.name);
    if (entry.isDirectory()) {
      if (depth > 0) found.push(...cssFiles(full, depth - 1));
      continue;
    }
    if (entry.name.endsWith(".css")) found.push(full);
  }
  return found;
}

const themeFiles = [
  ...readdirSync(THEMES_DIR).map((name) => resolve(THEMES_DIR, name)),
  resolve(SRC_DIR, "index.css"),
];

describe("暗色主题不取纯黑 / 纯白", () => {
  it("每个主题都取到了 --background 与 --foreground（解析本身不能空转）", () => {
    for (const file of themeFiles) {
      const map = tokens(readFileSync(file, "utf8"));
      expect(map["--background"], file).toBeTruthy();
      expect(map["--foreground"], file).toBeTruthy();
    }
  });

  it("暗色表面（背景 / 卡片 / 浮层）不落在 0% 或 100% 亮度", () => {
    const problems: string[] = [];
    for (const file of themeFiles) {
      const map = tokens(readFileSync(file, "utf8"));
      const background = map["--background"];
      if (!background || background.l >= 50) continue; // 亮色主题：见文件头的判定范围
      for (const key of SURFACES) {
        const token = map[key];
        if (!token) continue;
        if (token.l <= 0 || token.l >= 100) {
          problems.push(`${file} ${key}=${token.l}%`);
        }
      }
    }
    expect(problems).toEqual([]);
  });

  it("正文色：暗色不取纯白、亮色不取纯黑", () => {
    const problems: string[] = [];
    for (const file of themeFiles) {
      const map = tokens(readFileSync(file, "utf8"));
      const background = map["--background"];
      const foreground = map["--foreground"];
      if (!background || !foreground) continue;
      const dark = background.l < 50;
      if (dark && foreground.l >= 100) problems.push(`${file} 暗色正文取纯白`);
      if (!dark && foreground.l <= 0) problems.push(`${file} 亮色正文取纯黑`);
    }
    expect(problems).toEqual([]);
  });
});

describe("字重下限（小字号中文不糊）", () => {
  it("全仓没有 font-thin / font-extralight / font-light，也没有低于 400 的 font-weight", () => {
    const problems: string[] = [];
    for (const file of cssFiles(SRC_DIR)) {
      const css = readFileSync(file, "utf8");
      const match = css.match(/font-weight:\s*(\d{3})/);
      if (match && Number(match[1]) < 400) problems.push(`${file} font-weight:${match[1]}`);
    }
    for (const file of cssFiles(SRC_DIR).concat(
      readdirSync(SRC_DIR, { withFileTypes: true })
        .filter((entry) => entry.isFile() && entry.name.endsWith(".tsx"))
        .map((entry) => resolve(SRC_DIR, entry.name))
    )) {
      const source = readFileSync(file, "utf8");
      const hit = source.match(/font-(thin|extralight|light)\b/);
      if (hit) problems.push(`${file} ${hit[0]}`);
    }
    expect(problems).toEqual([]);
  });
});
