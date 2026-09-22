import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// U-1 的 UX 回归网（体检 UX-2 / UX-5 / FC-8）：
// * UX-2 记忆协议：切页签 → 整页刷新（指纹刷新会做的动作）→ 仍停在原页签；
// * UX-5 删除确认：危险操作先确认（点一次不落盘）——主题删除用 localStorage 计数断言；
// * FC-8 岗位池搜索：输入关键词只剩匹配行，清空恢复。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("进展页页签：切换后刷新仍停在原页签（UX-2）", async ({ page }) => {
  await openPage(page, "progress");
  // 英文界面（ENV_SCRIPT）页签名见 en.ts 的 progress.* 键
  await expect(page.getByRole("tab", { name: "Interviews" })).toHaveAttribute(
    "data-state",
    "active"
  );

  await page.getByRole("tab", { name: "Emails" }).click();
  await page.getByRole("tab", { name: "Contacts" }).click();
  await expect(page.getByRole("tab", { name: "Contacts" })).toHaveAttribute(
    "data-state",
    "active"
  );

  // 整页刷新 = 外部改动触发的指纹刷新的等效动作；记忆协议必须把用户放回原页签
  await page.reload();
  await expect(page.locator("nav").getByRole("combobox").first()).toBeVisible();
  await expect(page.getByRole("tab", { name: "Contacts" })).toHaveAttribute(
    "data-state",
    "active"
  );
});

test("投递行内快捷记录：一键落到对应页签（UX-4）", async ({ page }) => {
  await openPage(page, "applications");
  const expand = () => page.getByTitle("Expand details").first().click();

  await expand();
  await page.getByRole("button", { name: "Log interview" }).click();
  await expect(page).toHaveURL(/#progress$/);
  await expect(page.getByRole("tab", { name: "Interviews" })).toHaveAttribute(
    "data-state",
    "active"
  );

  // 换个入口再来一次：切页会重挂载，展开态复位属预期，重新展开即可
  await openPage(page, "applications");
  await expand();
  await page.getByRole("button", { name: "Log contact" }).click();
  await expect(page.getByRole("tab", { name: "Contacts" })).toHaveAttribute(
    "data-state",
    "active"
  );
});

test("删除自定义主题：先确认，点一次不落盘（UX-5）", async ({ page }) => {
  await openPage(page, "settings");
  // 编辑器默认折叠，先点开
  await page.getByRole("button", { name: "Custom theme" }).click();
  // 造一个自定义主题（保存当前变量，命名后入列）
  await page.getByLabel("Theme name").fill("e2e-check");
  await page.getByRole("button", { name: "Save as theme" }).click();
  // 名字会同时出现在主题选择器 radio 和编辑器列表行——按含 Delete 的行收窄
  const row = page
    .getByText("e2e-check", { exact: true })
    .locator("..")
    .filter({ has: page.getByRole("button", { name: "Delete" }) });
  await expect(row).toBeVisible();

  const dialog = page.getByRole("dialog");
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("Delete custom theme?");

  // 取消：主题还在
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(row).toBeVisible();

  // 确认：真的删除
  await row.getByRole("button", { name: "Delete" }).click();
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("e2e-check", { exact: true })).not.toBeVisible();
  await expect(page.getByText("Deleted", { exact: true })).toBeVisible();
});
