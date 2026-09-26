import { expect, test } from "@playwright/test";
import { ENV_SCRIPT, openPage } from "./fixtures";

// 工作区同步的「来源一致」回归（2026-09-26 修复）。
//
// 缺陷现场：localStorage 里存着一个当前数据根下**不存在**的工作区名（典型来源：
// 从 dev 栈切到安装版——两者数据根不同，dev 栈的 demo 在安装版里不存在），
// useBackendBoot 会优雅回退到默认工作区（界面一切正常），但 useWorkspaceSync
// 仍拿 localStorage 的旧名去轮询 → 每 10s 一次 404、「外部改动感知」（CLI / MCP
// 写完后切回 GUI 自动刷新）整条失效，只在控制台留一条 warn。
//
// 修复后钉住的核心断言：**指纹请求不许出现那个失效的工作区名**。

test("工作区残留失效值时：指纹轮询用已激活的默认工作区，不带残留名", async ({ page }) => {
  const fingerprintUrls: string[] = [];
  await page.addInitScript(ENV_SCRIPT);
  // 覆盖 ENV_SCRIPT 设的 demo：换成一个必然不存在的工作区名（模拟"选中值失效"）
  await page.addInitScript(() => {
    localStorage.setItem("jobws_selected_workspace", "no-such-workspace");
  });
  await page.route("**/api/system/workspace-version*", (route) => {
    fingerprintUrls.push(route.request().url());
    return route.fulfill({ json: { fingerprint: "fp-1" } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPage(page, "dashboard");

  // 首轮指纹请求在挂载即发出（useWorkspaceSync 的 void check() 只建立基线），
  // 不必等 10s 的轮询周期
  await expect.poll(() => fingerprintUrls.length, { timeout: 5000 }).toBeGreaterThan(0);
  for (const url of fingerprintUrls) {
    expect(url).not.toContain("no-such-workspace");
    expect(url).toContain("ws=");
  }
});
