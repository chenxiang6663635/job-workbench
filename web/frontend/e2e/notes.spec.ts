import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 笔记页签（03_面试准备 / 04_知识库 的只读浏览）——「准备」页的第三页签。
//
// 为什么必须显式点页签：openPage 只 goto 页面、等导航就绪，**不点页内页签**；
// smoke / a11y / themes 三套的既有循环因此覆盖不到笔记面板，这条 spec 是它
// 唯一的回归网。断言取真实目录名（不翻译）与 demo 内容里的中文标题（与界面
// 语言无关）；英文界面同时顺带验证了分组的双语形态。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  // 显式暗色（与 a11y.spec 的默认套同口径）：Playwright 默认 colorScheme=light，
  // 经「跟随系统」会落到浅色——这里先固定一种，浅色由 a11y 既有循环覆盖不到，
  // 本 spec 的 axe 扫描即代表本面板的 a11y 面。
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("笔记：左树、默认渲染与本页大纲", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();

  // 两个分组都出现；README 置顶显示为「Directory guide」
  await expect(page.getByText("Interview prep (03_面试准备)")).toBeVisible();
  await expect(page.getByText("Knowledge base (04_知识库)")).toBeVisible();
  await expect(page.getByText("Directory guide").first()).toBeVisible();

  // 默认选中第一个文件（demo 的 03 README）→ h1 与右侧大纲渲染出来
  await expect(
    page.getByRole("heading", { level: 1, name: "面试准备" })
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "On this page" })).toBeVisible();
});

test("笔记：切换文件、HTML 注释不渲染、a11y 零命中", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();

  // 切到行为故事模板：正文换成它独有的一节
  await page.getByRole("button", { name: "_模板_行为故事" }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "为什么用故事库而不是题库" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "对应的考察维度" })
  ).toBeVisible();
  // 模板里的 HTML 注释（填写说明）在渲染前剥除——不能作为文本出现
  await expect(page.locator("body")).not.toContainText("<!--");

  // 笔记面板纳入 a11y 扫描：serious / critical 零命中（与既有套同口径）
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `笔记页有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
});
