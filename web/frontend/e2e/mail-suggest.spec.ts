import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 邮件解析建议区（批 9）：键盘可达、逐条确认、忽略、低把握需先核对。
//
// 为什么全用路由拦截：真实 IMAP 拉取需要用户凭证（测试里不可能有），而建议区
// 只在拉取弹窗里出现。拦掉 `/api/imap/fetch` 与 `/api/imap/suggest-facts` 之后，
// 跑的是真实组件与真实请求代码，只是数据来自夹具。
// 写回也一并拦掉：demo 工作区在冒烟里必须**零改动**。

const ICS = [
  "BEGIN:VCALENDAR",
  "BEGIN:VEVENT",
  "DTSTART;TZID=Asia/Shanghai:20260925T140000",
  "SUMMARY:Technical interview",
  "URL:https://meeting.tencent.com/dm/abc123",
  "END:VEVENT",
  "END:VCALENDAR",
  "",
].join("\r\n");

const MESSAGES = [
  {
    uid: "1",
    subject: "Interview invitation",
    from: "hr@example.com",
    date: "2026-09-20 10:00",
    body: "Interview moved to 2026-09-25 14:00.",
    calendar: ICS,
    messageId: "abc@example.com",
  },
];

const FACTS = [
  {
    kind: "会议链接",
    value: "https://meeting.tencent.com/dm/abc123",
    label: "会议链接",
    evidence: "URL:https://meeting.tencent.com/dm/abc123",
    confidence: "high",
    source: "ics",
    targetId: "",
    note: "",
  },
  {
    kind: "时间",
    value: "2026-09-25 14:00",
    label: "时间",
    evidence: "Interview moved to 2026-09-25 14:00.",
    confidence: "low",
    source: "body",
    targetId: "A001",
    note: "原文没有年份，按 2026 年记，请确认",
  },
  {
    kind: "阶段",
    value: "一面",
    label: "建议阶段",
    evidence: "面试邀请",
    confidence: "high",
    source: "body",
    targetId: "A001",
    note: "",
  },
  {
    kind: "截止",
    value: "2026-09-25",
    label: "完成在线测评",
    evidence: "请在 2026-09-25 前完成在线测评。",
    confidence: "high",
    source: "body",
    targetId: "A001",
    note: "",
  },
];

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  // 用**正则**而不是 glob：应用的请求都带 `?ws=demo`，glob 模式会匹配不上
  await page.route(/\/api\/imap\/fetch/, (route) =>
    route.fulfill({
      json: {
        messages: MESSAGES,
        count: MESSAGES.length,
        server: "imap.example.com",
        folder: "INBOX",
        sinceDays: 30,
        dryRun: true,
        note: "",
      },
    })
  );
  await page.route(/\/api\/imap\/suggest-facts/, (route) =>
    route.fulfill({ json: { facts: FACTS, total: FACTS.length } })
  );
  await page.route(/\/api\/progress\/mails/, (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 201,
      json: { 邮件id: "M999", 主题: "Interview invitation" },
    });
  });
  await page.route(/\/api\/applications\/suggest-status/, (route) =>
    route.fulfill({
      json: {
        signals: [],
        dates: [],
        matches: [
          {
            id: "A001", 公司: "Demo", 岗位: "Engineer", 当前阶段: "已投",
            命中: "手动指定", 证据: ["面试邀请"], 建议阶段: "一面",
            可覆盖: true, 原因: "",
          },
        ],
        ambiguous: false,
        unmatched: false,
        ambiguous_match: false,
        notes: [],
      },
    })
  );
  await page.route(/\/api\/applications\/apply-status-suggestion/, (route) =>
    route.fulfill({ json: { item: { id: "A001", 当前阶段: "一面" } } })
  );
});

async function openSuggestions(page: Page): Promise<void> {
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Fetch from mailbox" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  // 键盘可达：聚焦后用回车展开（不是只能点鼠标）
  const toggle = page.getByRole("button", { name: "Suggestions" });
  await toggle.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("group", { name: "Meeting link" })).toBeVisible();
}

test("建议区：卡片含取值与原文出处，浮层 a11y 干净", async ({ page }) => {
  // 顺带钉住前端确实把日历附件传下去了（route mock 不看请求体，只有这里看）
  let posted: { ics?: string } | null = null;
  page.on("request", (req) => {
    if (req.url().includes("/api/imap/suggest-facts") && req.method() === "POST") {
      posted = req.postDataJSON();
    }
  });

  await openSuggestions(page);

  expect(posted!.ics).toContain("BEGIN:VCALENDAR");

  const card = page.getByRole("group", { name: "Meeting link" });
  await expect(card.getByText("https://meeting.tencent.com/dm/abc123", { exact: true }))
    .toBeVisible();
  await expect(card.getByText("URL:https://meeting.tencent.com/dm/abc123", { exact: true }))
    .toBeVisible();

  const results = await new AxeBuilder({ page })
    .include('[role="dialog"]')
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  const serious = results.violations.filter(
    (v) => v.impact === "serious" || v.impact === "critical"
  );
  expect(
    serious,
    `建议区有 serious/critical：${serious.map((v) => v.id).join("、")}`
  ).toEqual([]);
});

test("低把握项：勾选「我已核对取值」后才允许写入", async ({ page }) => {
  await openSuggestions(page);

  // 时间卡是低把握：它的写按钮初始不可用
  const card = page.getByRole("group", { name: "Time" });
  const write = card.getByRole("button", { name: "Write" });
  await expect(write).toBeDisabled();

  await card.getByRole("checkbox").check();
  await expect(write).toBeEnabled();
});

test("确认写入：卡片显示已写入，且只走既有台账链路", async ({ page }) => {
  await openSuggestions(page);

  let created: { 会议链接?: string } | null = null;
  page.on("request", (req) => {
    if (req.url().includes("/api/progress/mails") && req.method() === "POST") {
      created = req.postDataJSON();
    }
  });

  const card = page.getByRole("group", { name: "Meeting link" });
  await card.getByRole("button", { name: "Write" }).click();

  await expect(card.getByText("Written")).toBeVisible();
  expect(created).not.toBeNull();
  expect(created!.会议链接).toBe("https://meeting.tencent.com/dm/abc123");
});

test("AI 增强：Provider 就绪才出现，产出为需核对的建议", async ({ page }) => {
  await page.route(/\/api\/provider/, (route) =>
    route.fulfill({
      json: { base_url: "https://api.example.com/v1", api_key: "sk-***", hasKey: true },
    })
  );
  await page.route(/\/api\/imap\/suggest-facts-ai/, (route) =>
    route.fulfill({
      json: {
        facts: [
          {
            kind: "会议链接",
            value: "https://zoom.us/j/999",
            label: "会议链接",
            evidence: "Zoom 见",
            confidence: "low",
            source: "ai",
            targetId: "",
            note: "",
          },
        ],
        total: 1,
        model: "deepseek-chat",
      },
    })
  );

  await openSuggestions(page);
  await page.getByLabel("Model").fill("deepseek-chat");
  await page.getByRole("button", { name: "Run AI" }).click();

  // 新卡片出现、带 AI 角标，且仍是「需核对」档（写按钮默认不可用）
  const aiCard = page.getByRole("group", { name: "Meeting link: https://zoom.us/j/999" });
  await expect(aiCard).toBeVisible();
  await expect(aiCard.getByText("Needs check · AI")).toBeVisible();
  await expect(aiCard.getByRole("button", { name: "Write" })).toBeDisabled();
  await expect(page.getByText("AI suggestions from deepseek-chat")).toBeVisible();
});

test("截止事项：显示任务名与日期，写入同时落「下次动作日期」与「下次动作」", async ({ page }) => {
  // 写回拦截：真实 PATCH 会改 demo 工作区（冒烟必须零改动）
  await page.route(/\/api\/applications\/A001/, (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    return route.fulfill({ json: { item: { id: "A001" } } });
  });

  let patched: { 下次动作日期?: string; 下次动作?: string } | null = null;
  page.on("request", (req) => {
    if (req.url().includes("/api/applications/A001") && req.method() === "PATCH") {
      patched = req.postDataJSON();
    }
  });

  await openSuggestions(page);

  // 卡片把「要做什么」也显出来（label 是正文识别的任务名，不走 i18n）
  const card = page.getByRole("group", { name: "Deadline: 2026-09-25" });
  await expect(card).toBeVisible();
  await expect(card.getByText("完成在线测评", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Write" }).click();
  await expect(card.getByText("Written")).toBeVisible();

  // 这两个字段正是到点提醒（看板待办桶）读的：写进去即自动获得提醒
  expect(patched).not.toBeNull();
  expect(patched!.下次动作日期).toBe("2026-09-25");
  expect(patched!.下次动作).toBe("完成在线测评");
});

test("忽略一条后该卡片消失，其余卡片不受影响", async ({ page }) => {
  await openSuggestions(page);

  const linkCard = page.getByRole("group", { name: "Meeting link" });
  await linkCard.getByRole("button", { name: "Ignore" }).click();

  await expect(page.getByRole("group", { name: "Meeting link" })).toBeHidden();
  await expect(page.getByRole("group", { name: "Suggested stage" })).toBeVisible();
});

test("后端没给归属：卡片就地出现记录下拉，选定后写入（2026-09-25 真机缺陷）", async ({ page }) => {
  // 真实后端在零/多命中时 targetId 是空串——此前 UI 没有就地选定的出口，
  // 「确认写入」必然被 needRecord 拦死；本文件上方夹具的 mock 给了 A001，
  // 把这条断链盖住了。这里用**真实形状**（targetId 为空）钉住新出口。
  await page.route(/\/api\/imap\/suggest-facts/, (route) =>
    route.fulfill({
      json: {
        facts: [
          {
            kind: "链接有效期",
            value: "2026-10-02",
            label: "完成测评（链接即将失效）",
            evidence: "链接有效期：7天",
            confidence: "low",
            source: "body",
            targetId: "",
            note: "",
          },
        ],
        total: 1,
      },
    })
  );
  // 记录列表（ApplicationSelect 自取）与 PATCH 都拦掉：demo 工作区零改动
  await page.route(/\/api\/applications\/A001/, (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    return route.fulfill({ json: { item: { id: "A001" } } });
  });
  await page.route(/\/api\/applications\?/, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      json: {
        items: [
          { id: "A001", 公司: "Demo", 岗位: "Engineer", 当前阶段: "已投" },
        ],
        total: 1,
      },
    });
  });

  let patched: { 下次动作日期?: string; 下次动作?: string } | null = null;
  page.on("request", (req) => {
    if (req.url().includes("/api/applications/A001") && req.method() === "PATCH") {
      patched = req.postDataJSON();
    }
  });

  // 不用共享 helper：openSuggestions 硬断言「Meeting link」卡，而本用例的
  // 夹具只有一条链接有效期（真实形状）
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Fetch from mailbox" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  const toggle = page.getByRole("button", { name: "Suggestions" });
  await toggle.focus();
  await page.keyboard.press("Enter");

  const card = page.getByRole("group", { name: "Link expiry: 2026-10-02" });
  await expect(card).toBeVisible();
  const write = card.getByRole("button", { name: "Write" });

  // 未选定归属 → 写入禁用；下拉就地在卡片上（不再绕道完整解析对话框）
  await expect(write).toBeDisabled();

  await card.getByRole("combobox").click();
  await page.getByRole("option", { name: /A001/ }).click();

  // 低把握事实仍需先勾「我已核对取值」（既有纪律不被就地选定绕过）
  await card.getByRole("checkbox").check();
  await expect(write).toBeEnabled();
  await write.click();

  await expect(card.getByText("Written")).toBeVisible();
  expect(patched).not.toBeNull();
  expect(patched!.下次动作日期).toBe("2026-10-02");
  expect(patched!.下次动作).toBe("完成测评（链接即将失效）");
});

test("正文口径：拉取列表标「原文」、建议卡出处标「摘录」", async ({ page }) => {
  await openPage(page, "applications");
  await page.getByRole("button", { name: "Fetch from mailbox" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();

  // 列表预览是**原文**（保留引用与签名）——同一封邮件在建议卡里是另一种口径
  await expect(page.getByText("Quotes and signature kept").first()).toBeVisible();

  const toggle = page.getByRole("button", { name: "Suggestions" });
  await toggle.focus();
  await page.keyboard.press("Enter");

  // 出处是**剥掉引用与签名**的摘录：界面上必须说清，否则会被读成"两处正文不一致"
  await expect(page.getByText("Excerpt", { exact: true }).first()).toBeVisible();
});
