import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, PAGES, collectConsoleErrors, openPage } from "./fixtures";

// 主题遍历（批 4）：每套主题逐页 → data-theme 正确回写、无横向溢出、无控制台错误。
// 多主题最容易「某套主题某处溢出 / 报错」而人工只测默认暗——把遍历固化进冒烟
// （10 套 × 8 页；串行单 worker，约 1 分钟）。
const THEMES = [
  "dark",
  "light",
  "catppuccin-mocha",
  "catppuccin-latte",
  "nord",
  "tokyo-night",
  "rose-pine",
  "rose-pine-dawn",
  "gruvbox",
  "everforest",
] as const;

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("字体：正文栈含符号回退（CO₂ 下标 / 箭头不掉字）", async ({ page }) => {
  // 2026-09-20：内置界面 / 等宽字体都是"拉丁子集"，实测共同缺 ₂(U+2082) /
  // →(U+2192) / ≠ / ①；微软雅黑、宋体也缺 ₂。这里钉住**声明**（不是本机是否
  // 装了某款字体）：符号回退必须在栈里，否则回退受限的环境（打包版 / Linux /
  // 移动端）里正文的 CO₂ 下标、箭头会显示成空白。
  await openPage(page, "prepare");
  const stack = await page.evaluate(
    () => getComputedStyle(document.body).fontFamily
  );
  expect(stack).toContain("Segoe UI Symbol");
});

for (const theme of THEMES) {
  test(`主题 @ ${theme}：逐页属性回写、无溢出、无控制台错误`, async ({ page }) => {
    // 预写主题偏好：index.html 的防闪白内联脚本会读它并在首帧前写属性
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("jobws.theme", id);
      } catch {
        /* 隐私模式：交给后续断言暴露 */
      }
    }, theme);

    const errors = collectConsoleErrors(page);
    for (const key of PAGES) {
      await openPage(page, key);

      const attr = await page.evaluate(() =>
        document.documentElement.getAttribute("data-theme"),
      );
      if (theme === "dark") {
        expect(attr, "dark 主题不应写 data-theme（:root 即它）").toBeNull();
      } else {
        expect(attr, `${key} 的 data-theme 未回写为 ${theme}`).toBe(theme);
      }

      // 真生效断言（独立审查）：只查属性的话，主题文件为空壳、main.tsx 漏 import
      // 都会照样绿——按亮/暗语义校验 body 背景色（不依赖精确色值）。
      const bodyBg = await page.evaluate(
        () => getComputedStyle(document.body).backgroundColor
      );
      expect(bodyBg, "body 背景色未解析").not.toBe("rgba(0, 0, 0, 0)");
      const nums = (bodyBg.match(/\d+/g) ?? []).map(Number);
      const lightish = nums.length >= 3 && (nums[0] + nums[1] + nums[2]) / 3 > 150;
      if (["light", "catppuccin-latte", "rose-pine-dawn"].includes(theme)) {
        expect(lightish, `${key}（${theme}）背景应为亮色，实际 ${bodyBg}`).toBe(true);
      } else if (theme !== "dark") {
        expect(lightish, `${key}（${theme}）背景应为暗色，实际 ${bodyBg}`).toBe(false);
      }

      const overflow = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(
        overflow.scrollWidth,
        `${key} 在主题 ${theme} 下出现横向溢出`,
      ).toBeLessThanOrEqual(overflow.clientWidth + 1);

      expect(errors, `${key}（主题 ${theme}）控制台有错误`).toEqual([]);
    }
  });
}
