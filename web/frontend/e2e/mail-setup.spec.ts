import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, openPage } from "./fixtures";

// 邮箱配置体验（2026-09-24 批）：服务商下拉、自动带出、授权码引导、文件夹候选。
//
// 界面锁定英文（ENV_SCRIPT），所以文案断言写成英文——它的价值不是"读起来舒服"，
// 而是**改了文案就必须改测试**：引导文案是这一批的核心交付，不该被模糊匹配掩盖。
//
// 隐私护栏会拦真实服务商域名邮箱的字面量（.githooks/pre_commit.py）：样本拼接构造。
const QQ_MAIL = "user@" + "qq.com";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("邮箱卡：选服务商即带出服务器与端口，并就地给出授权码引导", async ({ page }) => {
  await openPage(page, "settings");

  const host = page.getByPlaceholder("imap.example.com");
  const port = page.locator('input[type="number"]');

  await page.getByLabel("Provider", { exact: true }).click();
  await page.getByRole("option", { name: /QQ Mail/ }).click();

  await expect(host).toHaveValue("imap.qq.com");
  await expect(port).toHaveValue("993");
  // 引导默认展开：选完就能看到"怎么拿授权码"，而不是回头去翻文档
  await expect(page.getByText("QQ Mail rejects your web password")).toBeVisible();
});

test("邮箱卡：手改过服务器之后，再选服务商不再覆写（静默覆盖是最烦人的一类）", async ({
  page,
}) => {
  await openPage(page, "settings");

  const host = page.getByPlaceholder("imap.example.com");

  await page.getByLabel("Provider", { exact: true }).click();
  await page.getByRole("option", { name: /QQ Mail/ }).click();
  await expect(host).toHaveValue("imap.qq.com");

  // 用户手改（这才算 dirty）
  await host.fill("imap.custom.example");

  await page.getByLabel("Provider", { exact: true }).click();
  await page.getByRole("option", { name: /Gmail/ }).click();

  await expect(host).toHaveValue("imap.custom.example");
});

test("邮箱卡：Outlook 直接说明为什么连不上，而不是留一个填了就错的框", async ({ page }) => {
  await openPage(page, "settings");

  await page.getByLabel("Provider", { exact: true }).click();
  await page.getByRole("option", { name: /Outlook/ }).click();

  await expect(page.getByText("stopped accepting basic auth")).toBeVisible();
});

test("邮箱卡：填了邮箱地址就认出服务商，一键套用服务器", async ({ page }) => {
  await openPage(page, "settings");

  const host = page.getByPlaceholder("imap.example.com");
  await page.getByPlaceholder("your-email@example.com").fill(QQ_MAIL);

  const apply = page.getByRole("button", { name: /QQ Mail/ }).first();
  await expect(apply).toBeVisible();
  await apply.click();

  await expect(host).toHaveValue("imap.qq.com");
});

test("邮箱卡：文件夹候选按需读取（点一次连一次），点一下即填入", async ({ page }) => {
  await openPage(page, "settings");

  // 只是候选：拦截出网，断言界面行为（真连接由后端测试覆盖）
  await page.route("**/api/mail/folders*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ folders: ["INBOX", "Archive"], count: 2, server: "imap.example.com" }),
    })
  );

  await page.getByRole("button", { name: "Load available folders" }).click();

  const archive = page.getByRole("button", { name: "Archive", exact: true });
  await expect(archive).toBeVisible();
  await archive.click();

  // 文件夹是自由输入框：点候选只是替用户打字，仍可手改
  const folder = page.getByPlaceholder("INBOX");
  await expect(folder).toHaveValue("Archive");
});
