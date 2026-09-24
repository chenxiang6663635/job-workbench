import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, openPage } from "./fixtures";

// 快照还原与演练的界面半笔（首发前收口批 笔 2）。钉住三件用静态检查测不到的事：
// 1. **演练是只读的**：跑完演练不该多出快照（列表行数不变），也不该落盘任何改动；
// 2. **「与当前一致」不放行**：刚备份完就点还原，界面应拒绝并说明原因；
// 3. **还原走确认词门禁**：主按钮在打字之前不可用，取消之后什么都没发生。
//
// 刻意不在 e2e 里真还原：还原会改写 demo 工作区的文件，后面的 spec 与后续调试都吃
// 它的状态（写路径已由 tests/test_snapshot_restore.py 用临时工作区覆盖）。
test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("快照：备份 → 演练（只读）→ 还原要过确认词门禁（收口批 笔 2）", async ({ page }) => {
  await openPage(page, "settings");

  const drillButtons = () => page.getByRole("button", { name: "Drill", exact: true });
  const restoreButtons = () => page.getByRole("button", { name: "Restore", exact: true });

  // 先备份一份出来（这一步本来就该是幂等的：写的是快照目录，不动工作区）
  await page.getByRole("button", { name: "Back up now" }).click();
  await expect(page.getByText(/Backed up \d+ files/)).toBeVisible();
  await expect(page.getByText("Restorable snapshots")).toBeVisible();

  const countBefore = await drillButtons().count();
  expect(countBefore).toBeGreaterThan(0);

  // ---- 演练：只读 + 如实报告「与当前一致」----
  await drillButtons().first().click();
  await expect(page.getByText(/Drill result:/)).toBeVisible();
  await expect(page.getByText(/Already identical \d+/)).toBeVisible();
  await expect(page.getByText(/The drill is read-only/)).toBeVisible();
  expect(await drillButtons().count()).toBe(countBefore);

  // ---- 「一致」时还原入口不放行：这是 canRestore 的判定，不是按钮藏起来 ----
  await restoreButtons().first().click();
  await expect(page.getByText(/nothing to restore/i)).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCount(0);

  // ---- 改动当前数据后，差异被检出、还原入口才放行 ----
  const changed = await page.request.patch("/api/applications/A001?ws=demo", {
    data: { 备注: `e2e-drill-${Date.now()}` },
  });
  expect(changed.ok(), await changed.text()).toBeTruthy();

  await drillButtons().first().click();
  await expect(page.getByText(/Overwrite \d+/)).toBeVisible();

  await restoreButtons().first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // 确认框正文里必须有「先给当前状态做一份快照」——那是这道门禁敢放开的前提
  await expect(dialog.getByText(/snapshot of the current state is taken first/)).toBeVisible();

  const confirm = dialog.getByRole("button", { name: "Restore to this point" });
  await expect(confirm).toBeDisabled();
  await dialog.getByLabel(/to confirm/).fill("restore");
  await expect(confirm).toBeEnabled();

  // ---- 取消 = 什么都没发生 ----
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  expect(await drillButtons().count()).toBe(countBefore);
});
