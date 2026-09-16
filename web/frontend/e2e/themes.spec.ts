import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, PAGES, collectConsoleErrors, openPage } from "./fixtures";

// 主题遍历（批 4）：每套主题逐页 → data-theme 正确回写、无横向溢出、无控制台错误。
// 多主题最容易「某套主题某处溢出 / 报错」而人工只测默认暗——把遍历固化进冒烟
// （10 套 × 7 页；串行单 worker，约 1 分钟）。
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

for (const theme of THEMES) {
  test(`主题 @ ${theme}：逐页属性回写、无溢出、无控制台错误`, async ({ page }) => {
    // 预写主题偏好：index.html 的防闪白内联脚本会读它并在首帧前写属性
    await page.addInitScript((id) => {
      try {
        localStorage.setItem("jobws.theme", id);
      } catch (e) {
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
