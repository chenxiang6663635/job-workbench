import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 「准备」页的页内页签（宣讲会 / 题库）——**openPage 只进页面、不点页内页签**，
// smoke / a11y / themes 三套既有循环因此覆盖不到这两个面板；这里各扫一次 axe，
// 把页内页签的覆盖缺口补上（笔记页签已由 notes.spec 覆盖，同一套姿势）。
//
// 这条网在 2026-09-19 之前是缺的——题库面板的两个搜索框一直缺 aria-label
// （axe 的 label 规则会报），却从没被任何扫描看到过。补齐输入框的可访问名称
// 之后，本 spec 就是这两个面板唯一的 a11y 回归网。

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  // 显式暗色（与 notes.spec 同口径）：Playwright 默认 colorScheme=light，
  // 经「跟随系统」会落到浅色——固定一种，扫描结果才稳定可复现。
  await page.addInitScript(() => {
    try {
      localStorage.setItem("jobws.theme", "dark");
    } catch {
      /* 隐私模式：交给断言失败暴露 */
    }
  });
  await page.setViewportSize({ width: 1440, height: 900 });
});

async function scanActiveTab(page: Page, tabName: string): Promise<void> {
  await page.getByRole("tab", { name: tabName }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  // 面板数据是异步拉的：等第一段真实内容出现（加载骨架是纯 div，不匹配这些）
  await expect(panel.locator("input, table, li, p").first()).toBeVisible({
    timeout: 10_000,
  });

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `${tabName} 面板有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
}

test("准备 · 宣讲会页签：a11y 零 serious/critical", async ({ page }) => {
  await openPage(page, "prepare");
  await scanActiveTab(page, "Talks");
});

test("准备 · 题库页签：a11y 零 serious/critical", async ({ page }) => {
  await openPage(page, "prepare");
  // 英文页签名是「Question bank」（不是 Questions——与语言包对齐）
  await scanActiveTab(page, "Question bank");
});

test("准备 · 训练页签：抽题后答案默认折叠（a11y 零 serious/critical）", async ({ page }) => {
  // 2026-09-20：训练面板是「练」的入口，核心纪律是**答案默认折叠**——先盲答再看。
  // 这条同时钉住"抽得到题"与"答案不在第一眼"。
  await openPage(page, "prepare");
  // 英文页签名是「Drill」（与语言包对齐）
  await page.getByRole("tab", { name: "Drill" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();

  // 用随机模式：demo 有两道「未看」恒在重练队列（队列不会空），其余四道的
  // due 状态随"今天是哪天"漂移；随机模式对日期完全免疫——本用例只关心
  // "抽得到题 + 答案默认折叠"，用最不依赖数据状态的模式。
  // 模式切换已改成 ui/segmented，单选是**原生 radio**（sr-only、1px 被裁切）——
  // 直接 click 会被外层 label 截住（smoke.spec 同款坑）。改为聚焦后按空格选中，
  // 顺带钉住"原生单选真的能选上"。
  const random = panel.getByRole("radio", { name: "Random" });
  await random.focus();
  await page.keyboard.press("Space");
  await expect(random).toBeChecked();
  await panel.getByRole("button", { name: "Draw" }).click();
  await expect(panel.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 10_000 });

  // 盲答：答案要点不给看；点开之后按钮消失（说明答案已展开）
  const reveal = panel.getByRole("button", { name: "Show answer" });
  await expect(reveal).toBeVisible();
  await reveal.click();
  await expect(panel.getByRole("button", { name: "Show answer" })).toHaveCount(0);

  const results = await new AxeBuilder({ page })
    .include('[role="tabpanel"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `训练面板有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
});

test("准备 · 训练页签：键盘自评后题目仍在原位（差异卡内联）", async ({ page }) => {
  // 2026-09-21：两件事一起钉——
  // ① 键盘能走完一轮（空格看答案 + 数字键自评）；
  // ② 自评弹出差异确认卡时，**题目还在**（此前整张题卡被差异卡替换，点完自评
  //    看不到刚答的题——确认写入时恰恰最需要对着题面核一眼）。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Drill" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();

  const random = panel.getByRole("radio", { name: "Random" });
  await random.focus();
  await page.keyboard.press("Space");
  await panel.getByRole("button", { name: "Draw" }).click();
  await expect(panel.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 10_000 });

  // 焦点还在「抽题」按钮上时按空格等于再点一次它——先失焦，让键盘交给面板
  await page.evaluate(() => {
    const el = document.activeElement;
    if (el instanceof HTMLElement) el.blur();
  });

  // 题面是题卡里唯一的 `text-base` 段（工具栏的字段名是 text-[11px]，不能取第一个 p）。
  // 断言走**这个元素本身**而不是按文字找——差异卡里的 diff 文本也含题面，按文字
  // 找会在"题卡被替换掉"时误判为还在。
  const question = panel.locator("p.text-base").first();
  await expect(question).toBeVisible();
  await page.keyboard.press("Space"); // 看答案
  await expect(panel.getByRole("button", { name: "Show answer" })).toHaveCount(0);

  // 用 W（标错题）触发预览：demo 的六道例题都没有「错题」标签，所以这一步一定
  // 产生差异（自评 1/2/3 若与当前状态相同会被领域层拒绝、直接跳下一题——那条
  // 路径下看不到确认卡，断言就不稳了）。
  await page.keyboard.press("w");

  // 差异确认卡内联在题目卡里：题目与"确认写入"同屏
  await expect(panel.getByRole("button", { name: "Confirm write" })).toBeVisible({
    timeout: 10_000,
  });
  await expect(question).toBeVisible();

  // Esc 关掉确认卡（键盘要能进也要能退），题目仍在
  await page.keyboard.press("Escape");
  await expect(panel.getByRole("button", { name: "Confirm write" })).toHaveCount(0);
  await expect(question).toBeVisible();
});

test("准备 · 题库详情的删除预览：a11y 零 serious/critical", async ({ page }) => {
  // 2026-09-20：新增的「删除确认卡」此前没有任何扫描覆盖过（它是弹窗里的第二层，
  // 只扫页签看不到）。删比改不可逆，这块的无障碍更不该是盲区。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Question bank" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  // demo 工作区自带例题：按题目文字定位行（行本身是 button，但导入按钮更靠前，
  // 不能取第一个 button）。题面必须与 template/demo/05_投递追踪/questions.csv 逐字一致——
  // 用本地工作区里存在、而 CI 的 demo 里没有的题面，这条用例在 CI 上必红。
  await panel.getByText("TCP 三次握手为什么不是两次").click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  // 删除只走**预览**（不落盘）：摘要是领域层给的中文，与界面语言无关
  await dialog.getByRole("button", { name: "Delete this question" }).click();
  await expect(dialog.getByText("删除 1 道题")).toBeVisible({ timeout: 10_000 });

  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `删除确认卡有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
});

test("准备 · 题库：新增题目表单能预览（不落盘）", async ({ page }) => {
  // 2026-09-21（批次 B-1）：加题入口从 CLI 挪进界面——此前空态文案把用户往命令行推。
  // 只走到「预览」为止、不点确认：demo 数据零改动（落盘段走全站唯一 apply 通道，
  // 已有 update / import 同源覆盖；这条网钉的是**入口与必填校验**真的在界面上）。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Question bank" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  await expect(panel.locator("input, table, li, p").first()).toBeVisible({ timeout: 10_000 });

  await panel.getByRole("button", { name: "New question" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();

  // 题目为空时「预览」不可用——必填校验在界面就先拦住（后端也有同一道闸）
  await expect(dialog.getByRole("button", { name: "Preview" })).toBeDisabled();

  await dialog.getByLabel("题目 (Question)").fill("e2e 新增预览演示");
  await dialog.getByRole("button", { name: "Preview" }).click();
  // 预览段真的打到了 preview-add：差异摘要回显题目（此时仍未落盘）
  await expect(dialog.getByText("新增题目：e2e 新增预览演示")).toBeVisible({ timeout: 10_000 });

  // 取消预览（差异卡收起、表单还在）——弹窗关掉后 demo 数据零改动
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog.getByText("新增题目：e2e 新增预览演示")).toHaveCount(0);
});

test("准备 · 题库/训练：到期标记与「为什么在队列里」可见（B-3）", async ({ page }) => {
  // 2026-09-21（批次 B-3）：抽题规则不该让用户猜"为什么是这道题"——
  // ① 列表行用「Due」徽章标出当日待复习（demo 六道例题今天都在 due 集合里：
  //    未看恒在、过期未复习也在；reason 挂在 title 上悬停可看）；
  // ② 训练题卡头部显示抽到这道题的原因。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Question bank" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Due").first()).toBeVisible({ timeout: 10_000 });

  await page.getByRole("tab", { name: "Drill" }).click();
  const drillPanel = page.getByRole("tabpanel");
  await expect(drillPanel).toBeVisible();
  // 默认的「重练队列」模式：抽到的第一道必然有原因——三种可能文案都在正则里
  await drillPanel.getByRole("button", { name: "Draw" }).click();
  await expect(drillPanel.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 10_000 });
  await expect(drillPanel.getByText(/还没学|从没复习过|已到期/)).toBeVisible();
});

test("准备 · 训练：本轮题表可跳题、可回退（C-2）", async ({ page }) => {
  // 2026-09-21（批次 C-2）：误点自评此前只能重抽整轮——现在题表（或 ← 键）回到那题。
  // 用随机模式保证抽满 5 题（全库 6 道，与"今天是哪天"无关）。
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Drill" }).click();
  const panel = page.getByRole("tabpanel");
  await expect(panel).toBeVisible();
  const random = panel.getByRole("radio", { name: "Random" });
  await random.focus();
  await page.keyboard.press("Space");
  await panel.getByRole("button", { name: "Draw" }).click();
  await expect(panel.getByText("Question 1 of 5")).toBeVisible({ timeout: 10_000 });

  // 题表：5 个格子，当前格 aria-current=step
  const map = panel.getByRole("group", { name: "This round" });
  await expect(map).toBeVisible();
  const cells = map.getByRole("button");
  await expect(cells).toHaveCount(5);
  await expect(cells.nth(0)).toHaveAttribute("aria-current", "step");

  // 点第 3 格直接跳过去；← 键回退一格（跳转一律收起答案——不剧透）
  await cells.nth(2).click();
  await expect(panel.getByText("Question 3 of 5")).toBeVisible();
  await page.evaluate(() => {
    const el = document.activeElement;
    if (el instanceof HTMLElement) el.blur();
  });
  await page.keyboard.press("ArrowLeft");
  await expect(panel.getByText("Question 2 of 5")).toBeVisible();
});

test("准备 · 训练页签：窄屏 390×844 无横向溢出", async ({ page }) => {
  // 训练的价值之一就是"碎片化"——窄屏（手机浏览器）不该出现横向滚动条。
  await page.setViewportSize({ width: 390, height: 844 });
  await openPage(page, "prepare");
  await page.getByRole("tab", { name: "Drill" }).click();
  const panel = page.getByRole("tabpanel");
  // 模式切换已改成 ui/segmented，单选是**原生 radio**（sr-only、1px 被裁切）——
  // 直接 click 会被外层 label 截住（smoke.spec 同款坑）。改为聚焦后按空格选中，
  // 顺带钉住"原生单选真的能选上"。
  const random = panel.getByRole("radio", { name: "Random" });
  await random.focus();
  await page.keyboard.press("Space");
  await expect(random).toBeChecked();
  await panel.getByRole("button", { name: "Draw" }).click();
  await expect(panel.getByText(/Question 1 of \d+/)).toBeVisible({ timeout: 10_000 });

  // 断言**面板自身**不横向溢出：整站 390px 适配属于另一批未做的计划
  // （顶栏导航在 390px 下本来就溢出，与本面板无关——拿整页宽度断言会误报）。
  const overflow = await page.evaluate(() => {
    const panel = document.querySelector('[role="tabpanel"]') as HTMLElement | null;
    return panel ? panel.scrollWidth - panel.clientWidth : -1;
  });
  expect(overflow, `训练面板自身横向溢出 ${overflow}px`).toBeLessThanOrEqual(1);
});
