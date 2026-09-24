import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, openPage } from "./fixtures";

// 设置页的「找得到 / 退得回 / 知道何时生效」（首发前收口批 笔 4）。
//
// 断言用的锚点刻意选**稳定的字面量**（placeholder、按钮名、主题名），而不是卡片标题文案：
// 标题会随语言包改，placeholder 与本测试的意图（这张卡在不在）无关但足够独特。
test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("设置页：搜索能收窄卡片，中文关键词也能命中（收口批 笔 4）", async ({ page }) => {
  await openPage(page, "settings");

  const providerCard = page.getByPlaceholder("https://api.xxx.ai/v1");
  const imapCard = page.getByPlaceholder("your-email@example.com");
  const themeCard = page.getByRole("button", { name: "Custom theme" });

  await expect(providerCard).toBeVisible();
  await expect(themeCard).toBeVisible();

  // 搜索词表里同时收中英写法：界面是英文，仍然能用中文搜到（反之亦然）
  await page.getByLabel("Search settings").fill("邮箱");
  await expect(imapCard).toBeVisible();
  await expect(providerCard).not.toBeVisible();
  await expect(themeCard).not.toBeVisible();

  await page.getByLabel("Search settings").fill("");
  await expect(themeCard).toBeVisible();

  // 分组：外部服务只剩 provider 与 imap 两张
  await page.getByRole("button", { name: "External services" }).click();
  await expect(providerCard).toBeVisible();
  await expect(imapCard).toBeVisible();
  await expect(themeCard).not.toBeVisible();

  // 全部还原默认（清空分组与搜索）
  await page.getByRole("button", { name: "All groups" }).click();
  await expect(themeCard).toBeVisible();
});

test("设置页：改过的项带标记、能单项还原，@modified 只看改过的（收口批 笔 4）", async ({
  page,
}) => {
  await openPage(page, "settings");

  // 改主题：状态卡里出现"已改"标记与还原按钮，并如实显示新值
  await page.getByRole("radio", { name: "Nord" }).click();
  await expect(page.getByText("Nord", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("changed", { exact: true }).first()).toBeVisible();

  // @modified：只剩"有被改项"的卡可见（数据类卡片全部隐藏）
  await page.getByLabel("Search settings").fill("@modified");
  await expect(page.getByText("Nord", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Back up now" })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Custom theme" })).toBeVisible();

  // 单项还原：主题回到 System，标记消失
  await page.getByLabel("Search settings").fill("");
  await page.getByRole("button", { name: "Reset", exact: true }).first().click();
  await expect(page.getByText("System", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("changed", { exact: true })).toHaveCount(0);
});
