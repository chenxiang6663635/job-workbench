# 求职工作台 · 前端（React + TypeScript + Vite）

构建链与运行方式见仓库根 [README](../../README.md) 与 [使用手册](../../docs/usage-guide.zh-CN.md)；本文只讲这个目录自己的约定。

## 脚本（Windows 记得用 `npm.cmd`）

| 命令 | 用途 |
|---|---|
| `npm run dev` | Vite dev server（开发模式；日常 UI 开发用 `web/start.ps1` 一键起后端+前端） |
| `npm run build` | 产出 `dist/`——**桌面端与 e2e 跑的都是它**，改完代码不 build 等于验旧代码 |
| `npm run test:unit` | Vitest 单测（**刻意不引 jsdom**，只收 `tests/unit/**`；纯函数不要 import `lib/http`——它会连带初始化 i18n，而 i18n 顶层碰 `document`） |
| `npx playwright test` | e2e（跑构建产物；跑前查 8765 残留后端、挪开 `test-results/`） |
| `npm run capture` | 8 页 × 中英截图（与 pytest 不能并行） |

## 目录约定

- `pages/` 页面容器（8 页）；`components/` 组件；`components/ui/*` 内部原语；`components/settings/` 设置页各卡（独立成文件：一卡一文件，Settings.tsx 只做编排）
- `lib/` 纯函数与领域类型（`domainTypes.ts` 是前后端契约的 TS 镜像）；`hooks/` 复用状态钩子；`i18n/locales/` 双语（`zh-CN.ts` 是 key 的单一真值，`en.ts` 用 `satisfies` 编译期钉住 key 集合一致）
- API 客户端分两层：`api.ts`（端点）+ `lib/http.ts`（请求/错误归一）——新增端点优先挂 `api.ts`，水位紧张时开 `lib/<域>Api.ts`（先例 `snapshotApi.ts` / `providerApi.ts`）

## 硬约束

- **规模水位只许变小**（`tools/size_allowlist.txt`）：登记文件加行会直接红；新能力进新文件，被改的旧文件同笔净减
- **文案一律走 `t()`**：key 双语同键同参；领域枚举取值不翻译（与 CLI / 数据文件共享契约）
- **主题 token**：不写死色值/字体，走 CSS 变量（`lint ui-tokens` / `lint themes` 两个闸门守着）
- 界面文案里 JSX 三元内不能写 `{/* */}` 注释；徽章与正文别放同一个文本节点（`getByText(exact)` 会拿到拼接结果）
