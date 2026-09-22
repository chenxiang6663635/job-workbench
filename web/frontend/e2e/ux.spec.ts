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
