import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, PAGES, collectConsoleErrors, openPage } from "./fixtures";

// 视口矩阵补点（T-2 批，2026-09-21）：
// ① 390×844 从「prepare 训练面板」扩到五个关键页（dashboard / applications /
//    jobs / progress / settings）；
// ② 英文态补一处非 1440 宽度（nav 的 8 tab 完整可见，在 1280 下再验一次）；
// ③ 主题补一处非 1280 宽度（themes 全量跑在默认 1280；1440 抽验一主题 × 逐页）。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

const MOBILE_PAGES = [
  // 每页的允许溢出余量 = 2026-09-21 实测现状（dashboard 306 / progress 126，
  // 其余 0）+ 4px 字体渲染余量。整站 390px 完整适配属于尚未实施的批次
  // （顶栏与看板网格在窄屏本就有溢出），这里钉的是「不继续变坏」：
  // 溢出突然增大（> 余量）就是新回归。
  { key: "dashboard", over: 306 },
  { key: "applications", over: 0 },
  { key: "jobs", over: 0 },
  { key: "progress", over: 126 },
  { key: "settings", over: 0 },
] as const;

for (const { key, over } of MOBILE_PAGES) {
  test(`390×844：${key} 能渲染、无控制台错误、溢出不超现状`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const errors = collectConsoleErrors(page);
    await openPage(page, key);

    // 不崩、不白屏：内容区与页头标题都在
    await expect(page.locator("main").first()).toBeVisible();
    await expect(page.getByRole("heading").first()).toBeVisible();
    expect(errors, `${key} 在 390px 下有控制台错误`).toEqual([]);

    const { docOver } = await page.evaluate(() => ({
      docOver:
        document.documentElement.scrollWidth - document.documentElement.clientWidth,
    }));
    expect(
      docOver,
      `${key} 在 390px 下横向溢出增大（现状 ${over}px，实测 ${docOver}px）`
    ).toBeLessThanOrEqual(over + 4);
  });
}

test("英文态 @ 1280：8 个 tab 全部完整可见（非 1440 补点）", async ({ page }) => {
  // nav.spec 已在 1440 钉过；这里补低一档——英文标签最长，1280 是「窗口拉窄 /
  // 系统缩放 125%」的等效宽度档（fixtures.VIEWPORTS 的 laptop 档同源）。
  // （1024 下 tab 条本来就横向滚动，属未做的整站适配批次，不在本网断言范围。）
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/#dashboard");
  await expect(page.locator("nav").getByRole("combobox").first()).toBeVisible();

  const scroller = page.locator("nav div.overflow-x-auto");
  await expect(scroller).toHaveCount(1);
  const tabs = scroller.locator("button");
  await expect(tabs, "顶栏应有 8 个页签（与 App.tsx 的 TABS 一致）").toHaveCount(8);

  const { scrollWidth, clientWidth } = await scroller.evaluate((el) => ({
    scrollWidth: el.scrollWidth,
    clientWidth: el.clientWidth,
  }));
  expect(
    scrollWidth,
    `tab 条溢出 ${scrollWidth - clientWidth}px：最后一个页签会被裁掉`
  ).toBeLessThanOrEqual(clientWidth);
});

test("主题 × 1440：catppuccin-mocha 逐页无溢出、无控制台错误", async ({ page }) => {
  // themes.spec 全量跑在默认 1280；这里把「主题 × 更宽视口」的交叉补一格。
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "catppuccin-mocha");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  const errors = collectConsoleErrors(page);

  for (const key of PAGES) {
    await openPage(page, key);
    const attr = await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme")
    );
    expect(attr, `${key} 的 data-theme 未回写`).toBe("catppuccin-mocha");
    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(
      overflow.scrollWidth,
      `${key} 在 1440px 下出现横向溢出`
    ).toBeLessThanOrEqual(overflow.clientWidth + 1);
  }
  expect(errors, "1440 逐页有控制台错误").toEqual([]);
});
