import { expect, type Page } from "@playwright/test";

/** 七个页面：与 App.tsx 的 TABS 一一对应（hash 路由，可直接刷新直达）。 */
export const PAGES = [
  "dashboard",
  "applications",
  "jobs",
  "resume",
  "progress",
  "library",
  "settings",
] as const;
export type PageKey = (typeof PAGES)[number];

/** 三个视口：1440 是截图宽度；1024 是「窗口拉窄 / 系统缩放 125%」的等效宽度。 */
export const VIEWPORTS = [
  { name: "wide-1440", width: 1440, height: 900 },
  { name: "laptop-1280", width: 1280, height: 800 },
  { name: "compact-1024", width: 1024, height: 768 },
];

/**
 * 测试环境固定：demo 工作区 + 英文界面。
 *
 * 两个都必须显式设置：
 * - 工作区：localStorage 里的 `jobws_selected_workspace` 会盖掉后端默认值
 *   （截图管线踩过这个坑，不设就会拍到真实 personal 工作区）；
 * - 语言：英文标签比中文长 2–4 倍，正是「顶栏被挤成两行」那个历史缺陷的问题现场。
 */
export const ENV_SCRIPT = `
  try {
    localStorage.setItem("jobws_selected_workspace", "demo");
    localStorage.setItem("jobws_lang", "en");
  } catch (e) { /* 隐私模式下不可用：交给后续断言失败暴露 */ }
`;

/** 收集控制台错误与未捕获异常（生产构建下不该有任何一条）。 */
export function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));
  return errors;
}

/**
 * 打开某个页面并等到「工作区就绪」。
 *
 * 就绪信号用导航栏的工作区选择器：它只在 `listWorkspaces` 返回后渲染，
 * 比等某个业务文案稳定（文案会随语言包改，选择器不会）。
 */
export async function openPage(page: Page, key: PageKey): Promise<void> {
  await page.goto(`/#${key}`);
  await expect(page.locator("nav").getByRole("combobox").first()).toBeVisible();
  await page.waitForLoadState("networkidle");
}

/**
 * 页面内脚本：数出导航栏里每个「直接含文字」的元素占了几行文字。
 *
 * **只对文字节点做 Range**，不要 selectNodeContents(el)：按钮里还有 svg 图标，
 * 图标的矩形 top 与文字不同，会把它误判成「折成了两行」——首跑时 21 个用例
 * 全红就是因为这个（断言先被自己的测量方式骗了）。
 */
export const NAV_LINE_COUNT = `
  (() => {
    const nav = document.querySelector("nav");
    if (!nav) return [{ text: "<nav missing>", lines: 0 }];
    const out = [];
    nav.querySelectorAll("*").forEach((el) => {
      const textNodes = Array.from(el.childNodes).filter(
        (n) => n.nodeType === 3 && (n.textContent || "").trim()
      );
      if (!textNodes.length) return;
      const tops = new Set();
      textNodes.forEach((node) => {
        const range = document.createRange();
        range.selectNodeContents(node);
        Array.from(range.getClientRects()).forEach((r) => tops.add(Math.round(r.top)));
      });
      out.push({ text: (el.textContent || "").trim().slice(0, 24), lines: tops.size });
    });
    return out;
  })()
`;
