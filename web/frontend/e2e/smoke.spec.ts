import { expect, test } from "@playwright/test";
import {
  ENV_SCRIPT,
  NAV_LINE_COUNT,
  PAGES,
  VIEWPORTS,
  collectConsoleErrors,
  openPage,
} from "./fixtures";

// 布局冒烟：三个视口 × 七个页面。
//
// 钉住的是历史缺陷，不是「设计规范」：
// ① 横向溢出（窄视口下最宽的追踪表会顶破页面）；
// ② 导航栏文字折行（2026-09-13 实测：英文标签被压成两行，按钮 36px → 56px，
//    tsc / eslint / 判定脚本三类静态检查全绿也发现不了）。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

for (const vp of VIEWPORTS) {
  test.describe(`布局 @ ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const key of PAGES) {
      test(`${key}：无横向溢出、导航不折行、无控制台错误`, async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await openPage(page, key);

        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(
          overflow.scrollWidth,
          `${key} 在 ${vp.width}px 下出现横向溢出`,
        ).toBeLessThanOrEqual(overflow.clientWidth + 1);

        const lines = (await page.evaluate(NAV_LINE_COUNT)) as {
          text: string;
          lines: number;
        }[];
        const wrapped = lines.filter((l) => l.lines > 1);
        expect(wrapped, `导航栏文字折行：${JSON.stringify(wrapped)}`).toEqual([]);

        expect(errors, `${key} 控制台有错误`).toEqual([]);
      });
    }
  });
}

test("语言切换立即改变导航文案与窗口标题，且不引入溢出", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openPage(page, "dashboard");
  const nav = page.locator("nav");

  await nav.getByRole("button", { name: "中文" }).click();
  await expect(nav.getByRole("button", { name: "看板" })).toBeVisible();
  // 窗口标题跟随语言：Electron 的窗口标题会被页面的 document.title 覆盖，
  // 不同步的话标题会永远停在 index.html 的静态值（2026-09-13 实测到的缺陷）
  await expect(page).toHaveTitle("求职工作台");

  await nav.getByRole("button", { name: "English" }).click();
  await expect(nav.getByRole("button", { name: "Dashboard" })).toBeVisible();
  await expect(page).toHaveTitle("Job Workbench");

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
});
