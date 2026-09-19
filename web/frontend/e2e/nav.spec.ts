import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, PAGES } from "./fixtures";

/**
 * 顶栏 tab 条不溢出（回归网）。
 *
 * 为什么需要它：**英文标签比中文长 2–4 倍**。2026-09-18 新增「准备」tab 后，
 * 1440 宽（内容区 `max-w-7xl` = 1280px）下 tab 条溢出 48px——第 8 个 tab
 * 「Settings」被裁成 `Set`，而界面上看不出那里还能横向滚。
 *
 * 既有冒烟只断言「**不折行**」（fixtures 的 `NAV_LINE_COUNT`），而这是**横滚**
 * 不是折行，所以整批检查都放它过去了：英文界面下导航少一个入口，CI 全绿。
 */
test.describe("顶栏", () => {
  test("1440 宽英文下，8 个 tab 全部完整可见", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.addInitScript(ENV_SCRIPT);
    await page.goto("/#dashboard");
    await expect(page.locator("nav").getByRole("combobox").first()).toBeVisible();

    const scroller = page.locator("nav div.overflow-x-auto");
    await expect(scroller).toHaveCount(1);

    const tabs = scroller.locator("button");
    await expect(tabs, "顶栏应有 8 个页签（与 App.tsx 的 TABS 一致）").toHaveCount(
      PAGES.length,
    );

    // ① 容器自身不该有横向滚动余量
    const { scrollWidth, clientWidth } = await scroller.evaluate((el) => ({
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
    }));
    expect(
      scrollWidth,
      `tab 条溢出 ${scrollWidth - clientWidth}px：最后一个页签会被裁掉`,
    ).toBeLessThanOrEqual(clientWidth);

    // ② 更贴近「看得见」的判据：每个 tab 的右边缘都落在容器内
    const container = await scroller.boundingBox();
    expect(container).not.toBeNull();
    for (const tab of await tabs.all()) {
      const label = (await tab.innerText()).trim();
      const box = await tab.boundingBox();
      expect(box).not.toBeNull();
      if (box && container) {
        expect(
          box.x + box.width,
          `页签「${label}」的右边缘超出容器`,
        ).toBeLessThanOrEqual(container.x + container.width + 1);
      }
    }
  });
});
