import { expect, test } from "@playwright/test";
import {
  ENV_SCRIPT,
  NAV_LINE_COUNT,
  PAGES,
  VIEWPORTS,
  collectConsoleErrors,
  openPage,
} from "./fixtures";

// 布局冒烟：三个视口 × 七个页面。
//
// 钉住的是历史缺陷，不是「设计规范」：
// ① 横向溢出（窄视口下最宽的追踪表会顶破页面）；
// ② 导航栏文字折行（2026-09-13 实测：英文标签被压成两行，按钮 36px → 56px，
//    tsc / eslint / 判定脚本三类静态检查全绿也发现不了）。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

for (const vp of VIEWPORTS) {
  test.describe(`布局 @ ${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    for (const key of PAGES) {
      test(`${key}：无横向溢出、导航不折行、无控制台错误`, async ({ page }) => {
        const errors = collectConsoleErrors(page);
        await openPage(page, key);

        const overflow = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          clientWidth: document.documentElement.clientWidth,
        }));
        expect(
          overflow.scrollWidth,
          `${key} 在 ${vp.width}px 下出现横向溢出`,
        ).toBeLessThanOrEqual(overflow.clientWidth + 1);

        const lines = (await page.evaluate(NAV_LINE_COUNT)) as {
          text: string;
          lines: number;
        }[];
        const wrapped = lines.filter((l) => l.lines > 1);
        expect(wrapped, `导航栏文字折行：${JSON.stringify(wrapped)}`).toEqual([]);

        expect(errors, `${key} 控制台有错误`).toEqual([]);
      });
    }
  });
}

test("七个页面的内容区宽度一致（宽度漂移是切页时肉眼可见的跳变）", async ({ page }) => {
  // 2026-09-13 实测到的缺陷：设置页自带 max-w-2xl —— 内容区 672px，其余六页 1232px，
  // 来回切 tab 时内容宽度整块跳变。宽度这种"看起来只是不好看"的问题没人会盯着，
  // 所以把它变成机检：**七页取到的宽度必须只有一个取值**。
  await page.setViewportSize({ width: 1440, height: 900 });
  const widths: Record<string, number> = {};
  for (const key of PAGES) {
    await openPage(page, key);
    widths[key] = await page.evaluate(() => {
      const content = document.querySelector("main")?.firstElementChild;
      return content ? Math.round(content.getBoundingClientRect().width) : -1;
    });
  }
  expect(
    new Set(Object.values(widths)).size,
    `内容区宽度不一致：${JSON.stringify(widths)}`,
  ).toBe(1);
});

test("岗位池排序与简历模式切换是原生单选组：方向键可切换", async ({ page }) => {
  // 这两处原来是 ui/tabs 当"单选开关"用：触发器带 aria-controls 指向不存在的内容面板
  // （axe 的 aria-valid-attr-value 报的就是它）。换成 ui/segmented 后用原生 radio，
  // 方向键切换与分组语义由浏览器给出——这条用例钉住"方向键真的能切"。
  await openPage(page, "jobs");
  const sortGroup = page.getByRole("radiogroup", { name: /Sort by/ });
  const first = sortGroup.getByRole("radio", { name: /Directory/ });
  await first.focus();
  await page.keyboard.press("ArrowRight");
  await expect(first).not.toBeChecked();
  // 组内**始终恰有一个**选中项：这是单选语义的核心（不会出现"都没选"或"多选"）。
  // 不写死"下一个是谁"——选项顺序会随排序维度增减而变，钉死它只会变成维护负担。
  const checked = await sortGroup
    .getByRole("radio")
    .evaluateAll((els) => els.filter((e) => (e as HTMLInputElement).checked).length);
  expect(checked).toBe(1);

  await openPage(page, "resume");
  const modeGroup = page.getByRole("radiogroup", { name: /Editing mode/ });
  const standard = modeGroup.getByRole("radio", { name: /Standard/ });
  await standard.focus();
  await page.keyboard.press("ArrowRight");
  await expect(modeGroup.getByRole("radio", { name: /Advanced/ })).toBeChecked();
});

test("语言切换立即改变导航文案与窗口标题，且不引入溢出", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await openPage(page, "dashboard");
  const nav = page.locator("nav");

  await nav.getByRole("button", { name: "中文" }).click();
  await expect(nav.getByRole("button", { name: "看板" })).toBeVisible();
  // 窗口标题跟随语言：Electron 的窗口标题会被页面的 document.title 覆盖，
  // 不同步的话标题会永远停在 index.html 的静态值（2026-09-13 实测到的缺陷）
  await expect(page).toHaveTitle("求职工作台");

  await nav.getByRole("button", { name: "English" }).click();
  await expect(nav.getByRole("button", { name: "Dashboard" })).toBeVisible();
  await expect(page).toHaveTitle("Job Workbench");

  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth + 1);
});
