import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import fs from "fs";
import { fileURLToPath } from "url";
import { ENV_SCRIPT, PAGES, openPage } from "./fixtures";

// 可访问性冒烟：七个页面各扫一次（wcag2a + wcag2aa），只对 serious / critical 失败。
//
// 「只对 serious/critical 失败」是刻意收窄：moderate/minor 里的 color-contrast
// 这类提示一次性会刷出几十条，修不完也审不完，结果一定是整条检查被绕过——
// 与 i18n 判定同一条纪律：**检查一旦烦人就会被绕过**。
//
// 豁免登记在 a11y-allowlist.json：页面 + 规则 id + 理由（禁整页豁免）。

type Allowlist = { pages: Record<string, Record<string, string>> };

function loadAllowlist(): Allowlist {
  const file = fileURLToPath(new URL("./a11y-allowlist.json", import.meta.url));
  if (!fs.existsSync(file)) return { pages: {} };
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Allowlist;
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(ENV_SCRIPT);
  await page.setViewportSize({ width: 1280, height: 900 });
});

for (const key of PAGES) {
  test(`a11y：${key}`, async ({ page }) => {
    await openPage(page, key);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const allow = loadAllowlist().pages[key] ?? {};
    const unexpected = results.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .filter((v) => !allow[v.id]);

    // 失败信息要能直接定位：规则 + 命中数 + 每条节点的选择器与 HTML 片段
    // （只报规则名的话，还得自己再跑一遍 axe 才知道是哪个按钮）
    const detail = unexpected
      .map((v) => {
        const nodes = v.nodes
          .slice(0, 5)
          .map((n) => `    - ${n.target.join(" ")}\n      ${n.html.slice(0, 120)}`)
          .join("\n");
        const more = v.nodes.length > 5 ? `\n    …共 ${v.nodes.length} 处` : "";
        return `${v.id}（${v.impact}）：${v.help}\n${nodes}${more}`;
      })
      .join("\n\n");
    expect(unexpected.length, `\n${detail}`).toBe(0);
  });
}
