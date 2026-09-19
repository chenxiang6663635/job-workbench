import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 素材库的事实卡渲染（2026-09-18：`<pre>` 原样 → 与「笔记」同款 Markdown 渲染）。
//
// demo 的 `00_事实库/` 有 `_模板_事实卡.md`：含表格、勾选框与 HTML 注释填写说明
// ——正好一次覆盖「渲染出来（表格）/ 注释剥掉」两个断言。素材库页不在既有
// smoke/a11y/themes 循环的**页内交互**覆盖面内（它们只进页面不点卡片），
// 这条是"打开一张事实卡"的唯一回归网。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("素材库：事实卡渲染成正文（表格）且 HTML 注释不出现", async ({ page }) => {
  await openPage(page, "library");

  // 打开模板事实卡（demo 里唯一的事实卡）
  await page.getByRole("button", { name: /_模板_事实卡/ }).click();

  // 表格渲染出来（「基本事实」表的表头）
  await expect(page.getByRole("columnheader", { name: "项" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "内容" })).toBeVisible();

  // HTML 注释（模板里的填写说明）在渲染前剥除——不能作为文本出现
  await expect(page.locator("main")).not.toContainText("<!--");
});
