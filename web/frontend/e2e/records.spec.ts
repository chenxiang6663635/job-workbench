import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 「记录删除」的 e2e（批 D 数据安全网）：GUI 删除走两段式——点行内删除 →
// 预览弹窗（列明将删的整行）→ Cancel 收场。**不真删**：e2e 对 demo 数据零改动
// （落盘段由 pytest 在真文件系统上覆盖，与题库删除先例同款）。
//
// 这条网同时钉住「旧版点两次直删」真的被撤掉了：旧交互的第一次点击只改按钮
// 外观、不发请求——那就不会有这个预览弹窗，断言会在「等弹窗」这一步失败。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("进展 · 邮件：删除走预览弹窗、Cancel 不落盘", async ({ page }) => {
  await openPage(page, "progress");
  await page.getByRole("tab", { name: "Emails" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  // 数据是异步拉的：等第一段真实内容出现（骨架是纯 div，不匹配这些）
  await expect(panel.locator("input, table, li, p").first()).toBeVisible({
    timeout: 10_000,
  });

  const rows = panel.getByRole("button", { name: "Delete record" });
  const before = await rows.count();
  expect(before).toBeGreaterThan(0);

  await rows.first().click();

  // 预览弹窗：摘要是领域层给的中文（与界面语言无关，题库删除先例同款），
  // 差异表（pre）列出将删的整行
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/删除邮件：M\d{3}/)).toBeVisible({ timeout: 10_000 });
  await expect(dialog.locator("pre")).toBeVisible();

  // Cancel：弹窗关、列表原样（demo 数据零改动——删除按钮数量不变）
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(rows).toHaveCount(before);
});

test("岗位池：删除走预览弹窗（列目录内文件）、Cancel 不落盘", async ({ page }) => {
  await openPage(page, "jobs");
  // 进某个岗位的详情：卡片主区是一个按钮，accessible name 含公司名
  await page.getByRole("button", { name: /示例科技/ }).first().click();

  const del = page.getByRole("button", { name: "Delete job" });
  await expect(del).toBeVisible();
  await del.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/删除岗位：示例科技_后端开发工程师/)).toBeVisible({
    timeout: 10_000,
  });
  // 差异表逐条列目录内文件——"将失去什么"的事前告知
  await expect(dialog.locator("pre")).toContainText("JD原文.md");

  // Cancel：关弹窗、目录还在（详情页仍显示删除入口）——demo 数据零改动
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
  await expect(del).toBeVisible();
});

test("岗位池：改名走表单 → 预览（列新旧目录名与 JD 首行）、Cancel 不落盘", async ({ page }) => {
  await openPage(page, "jobs");
  await page.getByRole("button", { name: /示例科技/ }).first().click();

  await page.getByRole("button", { name: "Rename job" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  // 表单预填当前值：改岗位名后再预览（同值会被领域层拒「新旧相同」）
  await dialog.locator("input").nth(1).fill("平台开发");
  await dialog.getByRole("button", { name: "Preview rename" }).click();

  await expect(
    dialog.getByText(/改名：示例科技_后端开发工程师 → 示例科技_平台开发/)
  ).toBeVisible({ timeout: 10_000 });
  // JD 首行标题同步列出（demo 的 JD 以 `# 公司 岗位` 开头）
  await expect(dialog.locator("pre")).toContainText("+ # 示例科技 平台开发");

  // Cancel：零改动
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toBeHidden();
});
