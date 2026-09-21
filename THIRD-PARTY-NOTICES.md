# 第三方依赖与许可声明

本仓库依赖以下第三方开源项目，感谢原作者。各依赖以其自带的许可证为准，此处仅为摘要，若有出入以原项目声明为准。

## Python 后端（`web/backend/requirements.txt`）

| 依赖 | 许可证 | 用途 |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | MIT | Web 框架 |
| [Starlette](https://github.com/encode/starlette)（FastAPI 依赖） | BSD-3-Clause | ASGI 工具集 |
| [uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI 服务器 |
| [pydantic](https://github.com/pydantic/pydantic) | MIT | 请求模型校验 |
| [pypdf](https://github.com/py-pdf/pypdf) | BSD-3-Clause | PDF 文本抽取与校验 |
| [certifi](https://github.com/certifi/python-certifi) | MPL-2.0 | 出网证书兜底（系统证书库不可用时随包分发的 CA 清单，仍严格校验） |

## 前端（`web/frontend/package.json`）

| 依赖 | 许可证 | 用途 |
|---|---|---|
| [React](https://github.com/facebook/react) / react-dom | MIT | UI 框架 |
| [recharts](https://github.com/recharts/recharts) | MIT | 图表 |
| [lucide-react](https://github.com/lucide-icons/lucide) | ISC | 图标 |
| [Vite](https://github.com/vitejs/vite) | MIT | 构建工具 |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 | 类型系统 |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) / tailwind-merge / tailwindcss-animate | MIT | 样式 |
| [PostCSS](https://github.com/postcss/postcss) / [autoprefixer](https://github.com/postcss/autoprefixer) | MIT | CSS 后处理 |
| [Radix UI](https://github.com/radix-ui/primitives)（`@radix-ui/react-*`） | MIT | 无障碍组件原语（对话框 / 标签页 / 下拉…） |
| [i18next](https://github.com/i18next/i18next) / [react-i18next](https://github.com/i18next/react-i18next) | MIT | 界面双语 |
| [clsx](https://github.com/lukeed/clsx) / [class-variance-authority](https://github.com/joe-bell/cva) / [tailwind-merge](https://github.com/dcastil/tailwind-merge) | MIT | 类名组合工具 |
| [react-markdown](https://github.com/remarkjs/react-markdown) / [remark-gfm](https://github.com/remarkjs/remark-gfm) | MIT | 笔记 / 素材库的 Markdown 渲染（随应用分发） |

## 字体（`web/frontend` 本地打包，经 [Fontsource](https://fontsource.org/) 分发）

全部为 **SIL OFL-1.1**，随应用离线分发；各字体的版权声明与许可证全文见对应 npm 包内 `LICENSE`。

| 字体 | 用途 |
|---|---|
| [Inter](https://fontsource.org/fonts/inter) · [Geist](https://fontsource.org/fonts/geist) · [IBM Plex Sans](https://fontsource.org/fonts/ibm-plex-sans) · [Manrope](https://fontsource.org/fonts/manrope) · [Plus Jakarta Sans](https://fontsource.org/fonts/plus-jakarta-sans) · [DM Sans](https://fontsource.org/fonts/dm-sans) | 界面字体选项（默认 Inter） |
| [Figtree](https://fontsource.org/fonts/figtree) · [Outfit](https://fontsource.org/fonts/outfit) · [Public Sans](https://fontsource.org/fonts/public-sans) · [Source Sans 3](https://fontsource.org/fonts/source-sans-3) · [Work Sans](https://fontsource.org/fonts/work-sans) · [Atkinson Hyperlegible Next](https://fontsource.org/fonts/atkinson-hyperlegible-next) | 界面字体选项 |
| [Maple Mono](https://fontsource.org/fonts/maple-mono) · [JetBrains Mono](https://fontsource.org/fonts/jetbrains-mono) · [Fira Code](https://fontsource.org/fonts/fira-code) · [Geist Mono](https://fontsource.org/fonts/geist-mono) · [IBM Plex Mono](https://fontsource.org/fonts/ibm-plex-mono) · [Source Code Pro](https://fontsource.org/fonts/source-code-pro) | 等宽字体选项（默认 Maple Mono）；其中 Geist Mono / IBM Plex Mono / JetBrains Mono 同时是数字字体槽候选（默认 Geist Mono） |

## 桌面壳（可选，`web/electron/`）

| 依赖 | 许可证 | 用途 |
|---|---|---|
| [Electron](https://github.com/electron/electron) | MIT | 桌面壳（其分发包含 Chromium 与 Node.js，各自遵循其许可） |
| [electron-updater](https://github.com/electron-userland/electron-builder) | MIT | 自动更新（随应用分发；只向本仓库的 GitHub Release 查询版本） |
| [electron-builder](https://github.com/electron-userland/electron-builder) | MIT | 打包工具 |

## 开发工具（不随产品分发）

| 工具 | 许可证 | 用途 |
|---|---|---|
| [git-filter-repo](https://github.com/newren/git-filter-repo) | GPL-2.0 | 历史清洗（仅维护者本地使用，不打包、不分发） |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | 测试 |
| [httpx](https://github.com/encode/httpx) | BSD-3-Clause | 测试用 HTTP 客户端（`fastapi.testclient` 依赖；仅开发） |
| [build](https://github.com/pypa/build) | MIT | 领域包构建（`jobws-core` 的 dev 依赖；仅开发） |
| [PyInstaller](https://github.com/pyinstaller/pyinstaller) | GPL-2.0-or-later（附随包例外条款） | 打包后端 exe；其 bootloader 进入打包产物，例外条款允许随非自由应用分发 |

## 数据与隐私

本项目**不含任何遥测或数据上报**。使用中产生的全部数据（岗位、投递、简历、面试记录）都保存在使用者本地的工作区目录，由使用者自行保管与备份。
