import { defineConfig, devices } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

// UI 冒烟（布局 + a11y）：单浏览器、单进程后端、少页面少断言。
//
// 为什么是「冒烟」不是「E2E 套件」：CONTRIBUTING 的「明确不做」把它限定在
// 「防静态检查测不到的回归」——2026-09-13 的实例是英文标签把顶栏挤成两行、
// 以及窗口标题被页面 title 覆盖，这两类 tsc / eslint / 判定脚本全都看不见。
// 业务流仍靠人工冒烟（发布流程第 1 步），这里只钉住「页面能开、不溢出、
// 不折行、无控制台错误、无 serious/critical 可访问性问题」。
const PORT = 8765;
const BASE_URL = `http://127.0.0.1:${PORT}`;
// package.json 是 "type": "module"，配置文件按 ESM 加载——没有 __dirname
const CONFIG_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(CONFIG_DIR, "..", "..");

export default defineConfig({
  testDir: "./e2e",
  // 单后端 + 单工作区：并行只会让页面互相抢数据，收益为零
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  timeout: 30_000,
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // 后端同源托管 web/frontend/dist，因此**不需要** vite dev server：
    // 一个进程即可，也免掉两进程编排带来的 flake 面。
    ...devices["Desktop Chrome"],
  },
  webServer: {
    // 解释器与 electron/main.js 同一约定：JOBWS_PYTHON 优先，其次 PATH 里的 python
    command: `${process.env.JOBWS_PYTHON || "python"} web/backend/main.py --workspace demo --port ${PORT}`,
    cwd: REPO_ROOT,
    url: `${BASE_URL}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    env: {
      // 起后端时不要弹浏览器窗口（UI 冒烟会反复拉起它）
      JOBWS_NO_BROWSER: "1",
    },
  },
});
