import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, openPage } from "./fixtures";

// 模型服务配置体验（2026-09-24 批）：服务商预设、默认模型、模型可点选、非阻断校验。
//
// 界面锁英文（ENV_SCRIPT）→ 文案断言写英文：改了文案就必须改测试，
// 因为这些文案正是本批的交付物。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("模型卡：选服务商预设即填入地址模板", async ({ page }) => {
  await openPage(page, "settings");

  const baseUrl = page.getByPlaceholder("https://api.xxx.ai/v1");
  await page.getByLabel("Provider preset").click();
  await page.getByRole("option", { name: "DeepSeek" }).click();

  await expect(baseUrl).toHaveValue("https://api.deepseek.com/v1");
});

test("模型卡：通义填了原生地址就当场提示（不阻断保存，只给出路）", async ({ page }) => {
  await openPage(page, "settings");

  const baseUrl = page.getByPlaceholder("https://api.xxx.ai/v1");
  await baseUrl.fill("https://dashscope.aliyuncs.com/api/v1");

  // 提示而非报错：文案说清"该换成什么"，不拦着用户保存
  await expect(page.getByText("DashScope (Qwen) needs the")).toBeVisible();
});

test("模型卡：测试连接后模型名可点选，点一下填入默认模型", async ({ page }) => {
  await openPage(page, "settings");

  await page.route("**/api/provider/test*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        status: 200,
        modelCount: 2,
        models: ["deepseek-chat", "deepseek-reasoner"],
        truncated: false,
        hint: "",
      }),
    })
  );

  await page.getByRole("button", { name: "Test provider connection" }).click();
  await expect(page.getByText("Available models (click to fill in)")).toBeVisible();

  await page.getByRole("button", { name: "deepseek-reasoner" }).click();

  // 默认模型是输入框：点胶囊只是替用户打字，仍可手改
  await expect(page.getByPlaceholder("deepseek-chat")).toHaveValue("deepseek-reasoner");
});
