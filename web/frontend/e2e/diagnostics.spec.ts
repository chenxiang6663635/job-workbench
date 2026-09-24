import { expect, test } from "@playwright/test";

import { ENV_SCRIPT, openPage } from "./fixtures";

// 诊断包导出（首发前收口批 笔 3）。这类"给报障用的出口"最容易在重构里被断掉，
// 而断掉的方式恰好是静态检查看不见的：链接还在、地址里少了 ?ws=，于是导出的是
// **默认工作区**的内容（issue #22 的形态）。这里既点链接也真的取一次字节。
test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
});

test("诊断包：设置页入口存在，且带上当前工作区真的能下载到 zip（收口批 笔 3）", async ({
  page,
}) => {
  await openPage(page, "settings");

  const link = page.getByRole("link", { name: "Export diagnostics" });
  await expect(link).toBeVisible();

  const href = await link.getAttribute("href");
  expect(href).toContain("/api/system/diagnostics");
  // 工作区必须显式带上：e2e 固定 demo，丢了这一段就会导出默认工作区的诊断
  expect(href).toContain("ws=demo");

  const res = await page.request.get(href as string);
  expect(res.status()).toBe(200);
  expect(res.headers()["content-type"]).toContain("zip");
  // zip 的幻数：确认拿到的是真包（而不是一段 HTML 错误页）
  const head = (await res.body()).subarray(0, 2).toString("latin1");
  expect(head).toBe("PK");
});
