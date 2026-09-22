import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 六个浮层的 a11y 扫描（T-2 批，2026-09-21）：页面级扫描（a11y.spec）只扫
// 静态页面，浮层要**先打开**才存在——它们是比页面更密的交互面（表单 / 差异表 /
// 危险操作确认），此前全在盲区里。每个浮层各扫一次，context 限定 `[role=dialog]`：
// 页面本体已由 a11y.spec 覆盖，这里只问"浮层自己干净不干净"。
// 全部只读到「打开 / 预览」为止，不点确认——demo 数据零改动。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1280, height: 900 });
});

async function scanDialog(page: Page, label: string): Promise<void> {
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  // 弹窗内容是异步来的：等第一段真实可交互元素出现再扫
  await expect(dialog.locator("input, textarea, select, button, pre").first())
    .toBeVisible({ timeout: 10_000 });
  // Radix 的 SelectValue 文本在挂载后的 effect 里才填进 trigger——刚打开的
  // 对话框里它可能还空着（页面级 Select 不暴露这个问题：openPage 等足了
  // networkidle，effect 早已跑完）。不等这一步，button-name 会时红时绿。
  // 注：Radix 的 SelectValue 文本在 axe 下偶发判为"不可见"（实测 textContent
  // 明明有值）——两个弹窗里的下拉已补显式 aria-label（T-2 修复），这里不再
  // 依赖 Radix 内部文本；若将来再有同类命中，先补 aria-label 而不是绕过扫描。

  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `${label} 有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
}

test("浮层 a11y：题库详情对话框", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Question bank" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  await panel.getByText("TCP 三次握手为什么不是两次").click();
  await scanDialog(page, "题库详情对话框");
});

test("浮层 a11y：投递状态解析（粘贴邮件）", async ({ page }) => {
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Paste email" }).click();
  await scanDialog(page, "状态解析对话框");
});

test("浮层 a11y：CSV 导入对话框", async ({ page }) => {
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Import CSV" }).click();
  await scanDialog(page, "CSV 导入对话框");
});

test("浮层 a11y：IMAP 拉取对话框", async ({ page }) => {
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Fetch from mailbox" }).click();
  await scanDialog(page, "IMAP 拉取对话框");
});

test("浮层 a11y：笔记勾选确认框", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();
  await page.getByRole("button", { name: "_模板_行为故事" }).click();
  const boxes = page.locator('input[type="checkbox"]');
  await expect(boxes.first()).toBeVisible();
  // 跨运行自愈（照 notes.spec 的审查 m6 修法）：上次中断若留下勾选，先翻回来
  if (await boxes.first().isChecked()) {
    await boxes.first().click();
    await page.getByRole("dialog").getByRole("button", { name: "Write" }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  }

  await boxes.first().click();
  await scanDialog(page, "笔记勾选确认框");
  // 只扫不写：取消掉，工作区零改动
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();
});

test("浮层 a11y：首启三步向导", async ({ page }) => {
  // 空库 → 引导卡 → 打开向导（造法与 smoke.spec 的「空库首页给引导」同款；
  // 响应按 DashboardData 的最小合法形状造，缺字段会先崩在 KPI 区）
  const emptyDashboard = {
    total: 0,
    active: 0,
    funnel: [],
    byDirection: [],
    byBatch: [],
    upcoming: [],
    overdue: [],
    stale: [],
    pending: [],
    staleDays: 7,
    retrospective: null,
    unappliedHigh: [],
    unappliedHighTotal: 0,
    scoreByState: [],
  };
  await page.route("**/api/dashboard**", (route) => route.fulfill({ json: emptyDashboard }));
  await page.goto("/#dashboard");
  await expect(page.locator("nav").getByRole("combobox").first()).toBeVisible();
  await page.getByRole("button", { name: "Create a workspace" }).click();
  await scanDialog(page, "首启三步向导");
});
