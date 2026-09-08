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

## 前端（`web/frontend/package.json`）

| 依赖 | 许可证 | 用途 |
|---|---|---|
| [React](https://github.com/facebook/react) / react-dom | MIT | UI 框架 |
| [recharts](https://github.com/recharts/recharts) | MIT | 图表 |
| [lucide-react](https://github.com/lucide-icons/lucide) | ISC | 图标 |
| [react-icons](https://github.com/react-icons/react-icons) | MIT | 图标 |
| [Vite](https://github.com/vitejs/vite) | MIT | 构建工具 |
| [TypeScript](https://github.com/microsoft/TypeScript) | Apache-2.0 | 类型系统 |
| [Tailwind CSS](https://github.com/tailwindlabs/tailwindcss) / tailwind-merge / tailwindcss-animate | MIT | 样式 |
| [PostCSS](https://github.com/postcss/postcss) / [autoprefixer](https://github.com/postcss/autoprefixer) | MIT | CSS 后处理 |

## 桌面壳（可选，`web/electron/`）

| 依赖 | 许可证 | 用途 |
|---|---|---|
| [Electron](https://github.com/electron/electron) | MIT | 桌面壳（其分发包含 Chromium 与 Node.js，各自遵循其许可） |
| [electron-builder](https://github.com/electron-userland/electron-builder) | MIT | 打包工具 |

## 开发工具（不随产品分发）

| 工具 | 许可证 | 用途 |
|---|---|---|
| [git-filter-repo](https://github.com/newren/git-filter-repo) | GPL-2.0 | 历史清洗（仅维护者本地使用，不打包、不分发） |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | 测试 |

## 数据与隐私

本项目**不含任何遥测或数据上报**。使用中产生的全部数据（岗位、投递、简历、面试记录）都保存在使用者本地的工作区目录，由使用者自行保管与备份。
