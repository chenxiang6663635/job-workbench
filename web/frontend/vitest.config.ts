import { defineConfig } from "vitest/config";

/**
 * 单元测试配置——**单独一份，不动 vite.config.ts**（那是打包用的）。
 *
 * 关键在 `include`：vitest 默认会收集 `**\/*.{test,spec}.?(c|m)[jt]s?(x)`，
 * 于是 `e2e/*.spec.ts`（Playwright 的冒烟用例）也会被当成单测收进来，
 * 在 node 环境里必然失败（2026-09-16 实测 3 个文件失败）。
 * 这里只收 `tests/unit/**\/*.test.ts`：单测是单测，e2e 由 `npm run test:ui` 跑。
 *
 * 目录也刻意放在 `src/` 之外（与 `e2e/` 平行）：单测里的中文是被测数据与用例
 * 说明，不是界面文案——放 `src/` 下会被 i18n 硬编码检查拦下（要登记十几条
 * 片段，且注释一改就腐化），挪出来就不必放宽任何门禁。
 *
 * environment 保持 node（不引 jsdom）：首批只测无 DOM 的纯逻辑，
 * 不为单测引入渲染环境，也不让单测去替代 e2e。
 */
export default defineConfig({
  test: {
    include: ["tests/unit/**/*.test.ts"],
    environment: "node",
  },
});
