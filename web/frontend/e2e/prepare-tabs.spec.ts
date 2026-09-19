import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 「准备」页的页内页签（宣讲会 / 题库）——**openPage 只进页面、不点页内页签**，
// smoke / a11y / themes 三套既有循环因此覆盖不到这两个面板；这里各扫一次 axe，
// 把页内页签的覆盖缺口补上（笔记页签已由 notes.spec 覆盖，同一套姿势）。
//
// 这条网在 2026-09-19 之前是缺的——题库面板的两个搜索框一直缺 aria-label
// （axe 的 label 规则会报），却从没被任何扫描看到过。补齐输入框的可访问名称
// 之后，本 spec 就是这两个面板唯一的 a11y 回归网。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  // 显式暗色（与 notes.spec 同口径）：Playwright 默认 colorScheme=light，
  // 经「跟随系统」会落到浅色——固定一种，扫描结果才稳定可复现。
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
});

async function scanActiveTab(page: Page, tabName: string): Promise<void> {
  await page.getByRole("tab", { name: tabName }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  // 面板数据是异步拉的：等第一段真实内容出现（加载骨架是纯 div，不匹配这些）
  await expect(panel.locator("input, table, li, p").first()).toBeVisible({
    timeout: 10_000,
  });

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `${tabName} 面板有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
}

test("准备 · 宣讲会页签：a11y 零 serious/critical", async ({ page }) => {
  await openPage(page, "prepare");
  await scanActiveTab(page, "Talks");
});

test("准备 · 题库页签：a11y 零 serious/critical", async ({ page }) => {
  await openPage(page, "prepare");
  // 英文页签名是「Question bank」（不是 Questions——与语言包对齐）
  await scanActiveTab(page, "Question bank");
});
