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

test("页面几何一致：根容器与 main 同宽、纵向节奏全站一致", async ({ page }) => {
  // 钉住两类"没人会盯着看"的漂移：
  // ① **页面根容器比 main 的内容盒窄**——2026-09-13 实测：设置页自带 max-w-2xl，
  //    内容区 672px，其余六页 1232px，切 tab 时宽度整块跳变；
  // ② **根容器内前两个可见子元素的间距不一致**——同日实测：简历页有三个根分支
  //    （高级模板 / 无版本 / 主分支），只改主分支会让另外两条仍是旧间距
  //    （独立审查抓到的 MAJOR：那是"无版本"用户首屏就会走到的路径）。
  //
  // **这条断言的能力边界**（别把它读成万能）：它只管**根容器**这一层。若某页把内容
  // 包进内层的 `mx-auto max-w-3xl`（超宽屏下居中窄栏是合理设计），它不会拦——
  // 那属于内层容器的事，也不该由它管。
  await page.setViewportSize({ width: 1440, height: 900 });
  const widths: Record<string, number> = {};
  const gaps: Record<string, number | string> = {};
  for (const key of PAGES) {
    await openPage(page, key);
    const m = await page.evaluate(() => {
      const main = document.querySelector("main");
      const root = main?.firstElementChild;
      if (!main || !root) return { root: -1, box: -1, gap: "n/a" };
      const cs = getComputedStyle(main);
      const box = Math.round(
        main.getBoundingClientRect().width -
          parseFloat(cs.paddingLeft) -
          parseFloat(cs.paddingRight),
      );
      const kids = [...root.children].filter((e) => e.getBoundingClientRect().height > 0);
      const gap =
        kids.length < 2
          ? "n/a"
          : Math.round(
              kids[1].getBoundingClientRect().top - kids[0].getBoundingClientRect().bottom,
            );
      return { root: Math.round(root.getBoundingClientRect().width), box, gap };
    });
    expect(m.root, `${key} 的根容器比 main 的内容盒窄（宽度漂移）`).toBe(m.box);
    widths[key] = m.root;
    gaps[key] = m.gap;
  }
  expect(new Set(Object.values(widths)).size, `内容区宽度不一致：${JSON.stringify(widths)}`).toBe(1);

  // 纵向节奏：只比较量得到的页面，但要求"量得到的"足够多——否则某个页面悄悄变成
  // 单子元素（比如被错误地整块条件渲染）会以"n/a"的形式把这条检查虚化掉。
  const numeric = Object.entries(gaps).filter(([, g]) => typeof g === "number");
  expect(
    numeric.length,
    `能量到纵向节奏的页面太少，检查被虚化：${JSON.stringify(gaps)}`,
  ).toBeGreaterThanOrEqual(5);
  expect(
    new Set(numeric.map(([, g]) => g)).size,
    `纵向节奏不一致（各页根容器内首两段的间距）：${JSON.stringify(gaps)}`,
  ).toBe(1);
});

test("岗位池排序与简历模式切换是原生单选组：方向键可切换", async ({ page }) => {
  // 用 `.focus()` 而不是 `.click()`：输入框是 `sr-only`（1px、被裁切），Playwright 的
  // 点击可用性检查会判它 "outside of the viewport" 而超时——要"点"就点它的 label。
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
