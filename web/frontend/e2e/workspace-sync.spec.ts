import { expect, test } from "@playwright/test";
import { openPage } from "./fixtures";

// 工作区同步的「来源一致」回归（2026-09-26 修复）。
//
// 缺陷现场：localStorage 里存着一个当前数据根下**不存在**的工作区名（典型来源：
// 从 dev 栈切到安装版——两者数据根不同，dev 栈的 demo 在安装版里不存在），
// useBackendBoot 会优雅回退到默认工作区（界面一切正常），但 useWorkspaceSync
// 仍拿 localStorage 的旧名去轮询 → 每 10s 一次 404、「外部改动感知」（CLI / MCP
// 写完后切回 GUI 自动刷新）整条失效，只在控制台留一条 warn。
//
// 修复分两层，**两条用例各钉一层**（独立审查 M1：只回滚任意一层时，单条"不带残留名"
// 的断言会因另一层仍在而假绿；所以这里一条做运行时改键、一条断言写回值）：
//   ① 来源统一：轮询读已激活的 currentWorkspace（用例 1 的运行时改键段专钉它）；
//   ② 持久化修正：失效选中值被写回为实际使用的工作区（用例 2 专钉它）。

/** 环境脚本一次到位：**不叠 fixtures 的 ENV_SCRIPT**——两次 addInitScript 的先后是
 *  隐式契约，一旦失效用例会悄悄变哑（残留值被 demo 顶掉而断言仍绿）。 */
function envScript(savedWorkspace: string): string {
  return `
    try {
      localStorage.setItem("jobws_selected_workspace", ${JSON.stringify(savedWorkspace)});
      localStorage.setItem("jobws_lang", "en");
    } catch (e) { /* 隐私模式下不可用：交给后续断言失败暴露 */ }
  `;
}

test("残留失效值：轮询用已激活工作区——挂载时与运行中改键后都不带残留名（钉住来源统一）", async ({
  page,
}) => {
  const urls: string[] = [];
  await page.addInitScript(envScript("no-such-workspace"));
  await page.route("**/api/system/workspace-version*", (route) => {
    urls.push(route.request().url());
    return route.fulfill({ json: { fingerprint: "fp-1" } });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPage(page, "dashboard");

  // 首轮指纹请求在挂载即发出（useWorkspaceSync 的 void check() 只建基线）
  await expect.poll(() => urls.length, { timeout: 5000 }).toBeGreaterThan(0);
  for (const url of urls) {
    expect(url).not.toContain("no-such-workspace");
    expect(url).toContain("ws=");
  }

  // **运行时把键改回失效值**再触发一次检查（onFocus 会立刻 check）：这一步专门钉住
  // 「来源统一」——若实现退回读 localStorage，新请求必然带残留名；读激活值的实现不带。
  urls.length = 0;
  await page.evaluate(() => {
    localStorage.setItem("jobws_selected_workspace", "no-such-workspace");
  });
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect.poll(() => urls.length, { timeout: 5000 }).toBeGreaterThan(0);
  for (const url of urls) {
    expect(url).not.toContain("no-such-workspace");
  }
});

test("失效选中值被写回为实际使用的工作区（钉住持久化修正）", async ({ page }) => {
  await page.addInitScript(envScript("no-such-workspace"));
  await page.setViewportSize({ width: 1440, height: 900 });
  await openPage(page, "dashboard");

  const saved = await page.evaluate(() =>
    localStorage.getItem("jobws_selected_workspace")
  );
  expect(saved).not.toBe("no-such-workspace");
  expect(saved).toBeTruthy();
});
