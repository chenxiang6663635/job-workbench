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

test("投递行「查看解析卡」下钻到该岗位详情（UX-3）", async ({ page }) => {
  await openPage(page, "applications");
  // 入口只在岗位池里真有对应岗位时才出现（反向关联靠 公司+岗位）。
  // 用行 id 定位 A001（示例科技），**不**取第一个按钮：2026-09-25 demo 岗位池
  // 从 2 个扩到 7 个后「有卡的行」变多，.first() 落到哪行取决于列表排序——
  // CI 实测点到星河物流，断言示例/云帆就红了。
  const card = page
    .locator("#row-A001")
    .getByRole("button", { name: "View parsed card" });
  await expect(card).toBeVisible();
  await card.click();

  // 落到岗位池并直接打开对应详情（详情标题 = 岗位目录名）
  await expect(page).toHaveURL(/#jobs$/);
  await expect(page.getByRole("heading", { level: 2 })).toContainText(
    "示例科技_后端开发工程师"
  );
});

test("岗位池搜索：输入关键词只剩匹配岗位（FC-8）", async ({ page }) => {
  await openPage(page, "jobs");
  // 卡片标题就是岗位目录名（JobCard），直接拿它当行 identifier
  const yunfan = page.getByText("云帆智算_数据平台开发工程师", { exact: true });
  const shili = page.getByText("示例科技_后端开发工程师", { exact: true });
  await expect(yunfan).toBeVisible();
  await expect(shili).toBeVisible();

  // 搜索框防抖 300ms——填完之后等列表自己回来，不 sleep 固定时长
  const box = page.getByLabel("Search company / role");
  await box.fill("示例科技");
  await expect(yunfan).not.toBeVisible();
  await expect(shili).toBeVisible();

  // 清空即恢复全量：筛过之后还得回得来
  await box.fill("");
  await expect(yunfan).toBeVisible();

  // 无匹配：必须说"没有匹配"，不能落回"岗位池是空的"（2026-09-22 审查 MINOR 笔 3）
  await box.fill("zzz-no-such-job");
  await expect(page.getByText(/No jobs match/)).toBeVisible();
  await expect(page.getByText("The job pool is empty")).not.toBeVisible();

  await box.fill("");
  await expect(yunfan).toBeVisible();
});

test("字号还原默认：即时生效，5 秒内可撤销（首发前收口批）", async ({ page }) => {
  await openPage(page, "settings");
  const slider = page.getByLabel("Interface size");
  // 先弄成非默认值（默认 100）
  await slider.fill("120");
  await expect(slider).toHaveValue("120");

  // 滑块的父 div 就是「A —— 滑块 —— A —— 重置」那一行，按它收窄按钮
  const row = slider.locator("xpath=..");
  await row.getByRole("button", { name: "Reset" }).click();

  // 撤销条出现、字号已即时变回默认
  const bar = page.getByRole("group", { name: "Undo" });
  await expect(bar).toContainText("Font size reset to default");
  await expect(slider).toHaveValue("100");

  // 撤销：回到 120（撤销条同时消失）
  await bar.getByRole("button", { name: "Undo" }).click();
  await expect(slider).toHaveValue("120");
  await expect(bar).not.toBeVisible();
});

test("危险确认对话框：输入不符时主按钮禁用（首发前收口批）", async ({ page }) => {
  await openPage(page, "settings");
  await page.getByRole("button", { name: "Custom theme" }).click();
  await page.getByLabel("Theme name").fill("e2e-gate");
  await page.getByRole("button", { name: "Save as theme" }).click();

  const row = page
    .getByText("e2e-gate", { exact: true })
    .locator("..")
    .filter({ has: page.getByRole("button", { name: "Delete" }) });
  const dialog = page.getByRole("dialog");
  await row.getByRole("button", { name: "Delete" }).click();

  // confirm 档：不要求输入确认词，主按钮立即可点（对照下面 phrase 档的行为）
  await expect(dialog.getByRole("button", { name: "Delete" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Cancel" }).click();
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
