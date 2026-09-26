import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 提醒条的 e2e（提醒条批，PR #221）。
//
// 为什么走 mock 而不是真数据：条会不会出现取决于 demo 数据的**绝对日期**与跑测机器的
// 「今天」——真数据下它只在特定日期浮现，钉不住。交付前的真数据验证是人工做的
// （见 PR 评论），自动化这条用 route mock 钉住三件事：显示判定 / hash 跳转 / 开关。
//
// 语言：ENV_SCRIPT 固定英文界面，所以断言用英文文案。

const DUE = {
  date: "2026-09-26",
  workspace: "demo",
  window: 3,
  counts: { todos: 2, talks: 1, overdue: 3 },
  todos: [],
  talks: [],
  overdue: [],
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("提醒条：有到点事项时渲染三类计数，点「已过期」跳追踪表且常驻", async ({ page }) => {
  await page.route("**/api/reminders/due*", (route) => route.fulfill({ json: DUE }));
  await openPage(page, "dashboard");

  const bar = page.getByLabel("Due today");
  await expect(bar).toBeVisible();
  await expect(bar.getByText("3 overdue")).toBeVisible();
  await expect(bar.getByText("2 to-dos in the next 3 days")).toBeVisible();
  await expect(bar.getByText("1 talk")).toBeVisible();

  await bar.getByText("3 overdue").click();
  await expect(page).toHaveURL(/#applications/);
  // 常驻：切页之后还在（Bar 挂在 <main> 里，不属于任何页面）
  await expect(bar).toBeVisible();
});

test("提醒条：无到点事项时整条不渲染（不留空壳）", async ({ page }) => {
  await page.route("**/api/reminders/due*", (route) =>
    route.fulfill({ json: { ...DUE, counts: { todos: 0, talks: 0, overdue: 0 } } }),
  );
  await openPage(page, "dashboard");
  await expect(page.getByLabel("Due today")).toHaveCount(0);
});

test("提醒条：桌面壳里「到点提醒」开关关掉后不渲染（读的是主进程偏好）", async ({ page }) => {
  await page.route("**/api/reminders/due*", (route) => route.fulfill({ json: DUE }));
  // mock 桌面偏好通道（浏览器形态没有它，这里是模拟桌面壳）：开关为关。
  // 本用例只用到 get；其余方法给最小实现，避免应用其他部分拿到 undefined。
  await page.addInitScript(() => {
    const snap = {
      level: 0, min: -3, max: 3, step: 0.5, percent: 100,
      lang: "en", reminders: false, reminderDays: 3, workspace: "",
    };
    (window as unknown as { jobwsPrefs?: unknown }).jobwsPrefs = {
      get: async () => snap,
      setZoomLevel: async () => ({ level: 0, percent: 100 }),
      setLang: async () => ({ lang: "en" }),
      setWorkspace: async () => ({ workspace: "" }),
      setReminders: async () => ({ reminders: false, reminderDays: 3 }),
      onZoomChanged: () => () => {},
      onReminderFocus: () => () => {},
    };
  });
  await openPage(page, "dashboard");
  await expect(page.getByLabel("Due today")).toHaveCount(0);
});
