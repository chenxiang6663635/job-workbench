import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

/**
 * 符号回退槽的声明级回归网（2026-09-20）。
 *
 * 为什么放在单测而不是只靠 e2e：e2e 的「正文栈含符号回退」只覆盖默认
 * `data-font` 下 **body** 的一条栈；`--font-mono-stack` / `--font-numeric-stack` /
 * `html[data-font="system"]` / `html[data-font="serif"]` 这四处没有任何网
 * （独立审查 OBSERVATION）。这里钉的是**声明**：槽有定义、且五处引用都在。
 *
 * 读文件用 node:fs（vitest 的 environment 就是 node）：不要用 Vite 的 `?raw`
 * ——本仓 vitest 配置未开 CSS 处理，CSS 的 `?raw` 导入拿到的是空串（2026-09-20
 * 实测：断言报 `expected '' to match …`）。
 */
const here = dirname(fileURLToPath(import.meta.url));
const indexCss = readFileSync(resolve(here, "../../src/index.css"), "utf8");

describe("字体栈的符号回退槽", () => {
  it("--font-symbols 有定义且含系统符号字体", () => {
    expect(indexCss).toMatch(/--font-symbols:\s*"Segoe UI Symbol"/);
    expect(indexCss).toContain('"Apple Symbols"');
    expect(indexCss).toContain('"Noto Sans Symbols 2"');
  });

  it("五条字体栈都引用了 --font-symbols（sans / mono / numeric / system / serif）", () => {
    const refs = indexCss.match(/var\(--font-symbols\)/g) ?? [];
    expect(refs.length).toBeGreaterThanOrEqual(5);
  });

  it("槽内不含 Malgun Gothic（韩文字体带汉字码位，会劫持 mono 栈里的中文回退）", () => {
    // 只看声明的值——注释里为了说明原因同样会出现这个词（首次实现就踩过：
    // 裸 toContain 全文件会因注释而红）。
    const decl = indexCss.match(/--font-symbols:([\s\S]*?);/);
    expect(decl?.[1] ?? "").not.toContain("Malgun Gothic");
  });
});
