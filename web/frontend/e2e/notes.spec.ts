import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 笔记页签（03_面试准备 / 04_知识库 的只读浏览）——「准备」页的第三页签。
//
// 为什么必须显式点页签：openPage 只 goto 页面、等导航就绪，**不点页内页签**；
// smoke / a11y / themes 三套的既有循环因此覆盖不到笔记面板，这条 spec 是它
// 唯一的回归网。断言取真实目录名（不翻译）与 demo 内容里的中文标题（与界面
// 语言无关）；英文界面同时顺带验证了分组的双语形态。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  // 显式暗色（与 a11y.spec 的默认套同口径）：Playwright 默认 colorScheme=light，
  // 经「跟随系统」会落到浅色——这里先固定一种，浅色由 a11y 既有循环覆盖不到，
  // 本 spec 的 axe 扫描即代表本面板的 a11y 面。
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
});

test("笔记：左树、默认渲染与本页大纲", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();

  // 两个分组都出现；README 置顶显示为「Directory guide」
  await expect(page.getByText("Interview prep (03_面试准备)")).toBeVisible();
  await expect(page.getByText("Knowledge base (04_知识库)")).toBeVisible();
  await expect(page.getByText("Directory guide").first()).toBeVisible();

  // 默认选中第一个文件（demo 的 03 README）→ h1 与右侧大纲渲染出来
  await expect(
    page.getByRole("heading", { level: 1, name: "面试准备" })
  ).toBeVisible();
  await expect(page.getByRole("navigation", { name: "On this page" })).toBeVisible();
});

test("笔记：切换文件、HTML 注释不渲染、a11y 零命中", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();

  // 切到行为故事模板：正文换成它独有的一节
  await page.getByRole("button", { name: "_模板_行为故事" }).click();
  await expect(
    page.getByRole("heading", { level: 2, name: "为什么用故事库而不是题库" })
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 2, name: "对应的考察维度" })
  ).toBeVisible();
  // 模板里的 HTML 注释（填写说明）在渲染前剥除——不能作为文本出现
  await expect(page.locator("body")).not.toContainText("<!--");

  // 笔记面板纳入 a11y 扫描：serious / critical 零命中（与既有套同口径）
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `笔记页有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
});

test("笔记：勾选框可翻转（预览 → 确认 → 落盘 → 重拉），用例自恢复", async ({
  page,
}) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();
  await page.getByRole("button", { name: "_模板_行为故事" }).click();

  const boxes = page.locator('input[type="checkbox"]');
  await expect(boxes.first()).toBeVisible();
  // demo 基准里这些都是未勾选——本用例末尾翻回去，不把痕迹留在工作区里
  expect(await boxes.first().isChecked()).toBe(false);

  await boxes.first().click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Flip this checkbox?")).toBeVisible();
  // 差异同时给出原行与新行——确认之前就能看清落到哪里、改了什么
  await expect(dialog.locator("pre")).toContainText("- - [ ]");
  await expect(dialog.locator("pre")).toContainText("+ - [x]");

  // 确认框本身也是新的可交互面：一并纳入扫描
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `勾选确认框有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);

  // 落盘走既有写通道（/api/approvals/apply），本页不发第二处写请求
  await dialog.getByRole("button", { name: "Write" }).click();
  await expect(dialog).toBeHidden();
  // 真值在文件里——重拉后勾选框才翻（本地不做乐观翻转）
  await expect(boxes.first()).toBeChecked();

  // 自恢复：再翻一次回到基准状态
  await boxes.first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("dialog").getByRole("button", { name: "Write" }).click();
  await expect(boxes.first()).not.toBeChecked();
});

test("笔记：全文搜索 → 点结果 → 打开并定位到命中行", async ({ page }) => {
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();

  // 关键词用 demo 正文里的中文（与界面语言无关，语言包改动不会打碎这条用例）；
  // 搜索框的可访问名由 aria-label 提供（placeholder 不是可访问名称）。
  // 可访问名由 aria-label 提供（placeholder 不是可访问名称）；input 未设
  // type=search，隐式 role 是 textbox（原生 search 的清除按钮会与自绘的清空
  // 按钮重复，故不设）
  await page.getByRole("textbox", { name: "Search file names and text…" })
    .fill("为什么用故事库");

  const hit = page.getByRole("button", { name: /为什么用故事库/ }).first();
  await expect(hit).toBeVisible();
  await hit.click();

  // 打开的是那份模板，且命中行所在块滚进了视口（不是"打开了但停在顶部"）
  const heading = page.getByRole("heading", {
    level: 2,
    name: "为什么用故事库而不是题库",
  });
  await expect(heading).toBeVisible();
  await expect(heading).toBeInViewport();

  // 命中词高亮（B-5）：结果条目里 <mark> 包住关键词——"搜到了"之外还能"看出命中的是哪几个字"
  await expect(page.locator("mark").first()).toBeVisible();

  // 结果列表是新出现的交互面：一并纳入 a11y 扫描
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `搜索结果有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);

  // 搜索态会把左栏目录树整体替换（B-6）——点「返回目录树」明确回来，
  // 不用先想到"清空输入框"这一层
  await page.getByRole("button", { name: "Back to file tree" }).click();
  await expect(page.getByRole("button", { name: "_模板_行为故事" })).toBeVisible();
});

test("笔记：普通列表项的正文要渲染出来（回归：li 分支曾漏渲染 children）", async ({
  page,
}) => {
  // 2026-09-20 实测缺陷：NotesMarkdown 的 li 映射在「非任务项」分支漏渲染
  // children，页面上只剩编号/圆点、正文全部消失（任务项分支正常，所以既有
  // 勾选框用例照不出它）。这条用例盯的是**正文字符串必须可见**。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Notes" }).click();
  await page.getByRole("button", { name: "_模板_自我介绍" }).click();

  // 60 秒版 / 30 秒版 是阅读区里的两条**平级**无序列表项（不是嵌套列表）；
  // 断言落到列表项自身的**正文纯文本**——缺陷复现时 li 只剩标记、纯文本为空。
  // （独立审查 MINOR：此前用 `page.locator("li").first()` 会命中左栏文件树，
  //   那个 li 在缺陷下照样有文字，属空转。）
  await expect(page.getByRole("heading", { level: 1 }).first()).toBeVisible();
  await expect(
    page.locator("li", { hasText: "60 秒版" }).first()
  ).toContainText("保留钩子");
  await expect(
    page.locator("li", { hasText: "30 秒版" }).first()
  ).toContainText("只留钩子");
});
