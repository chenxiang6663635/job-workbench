# Changelog

本项目的所有显著变更记录于此文件。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（0.x 阶段简化规则见 [CONTRIBUTING.md](CONTRIBUTING.md)）。

**版本号唯一来源**：`web/electron/package.json` 的 `version` 字段。
**尚未打任何 tag**：以下内容全部归入 `Unreleased`。首次正式发布时，将本段整体转为 `0.1.0` 并标注日期。

**取材原则**：只记录对使用者可见的软件变更（功能 / 修复 / 破坏性变更）。向工作区录入个人数据（岗位评分、事实补齐等）属于数据操作，不是软件变更，不入此册。

## [Unreleased]

### Added

- 本地 Web 原型：看板、投递追踪表、岗位池三个页面，FastAPI 后端直接复用 `tools/` 脚本读写同一份 Markdown/CSV 数据。
- 素材库页面：简历工坊与事实库的文件浏览、PDF/图片内联预览。
- 一键启动脚本（`web/start.ps1`）：起停前后端、等待就绪、自动打开浏览器；含依赖预检（python/node/npm）、端口占用诊断、前端启动失败的分类人话提示。
- 岗位详情页评分下钻：总分 → 四维 → 逐条命中明细（能力分层徽章 + 证据标签徽章）。
- 资格硬门槛前置：解析卡的硬门槛结论（通过/不通过/待确认三态）置顶展示于分数之上。
- 工作区一等概念：后端支持 `--workspace` 参数与环境变量指定默认工作区；`/api/workspaces` 列出可用工作区；前端导航栏切换下拉，所有请求携带工作区参数，多工作区数据隔离。
- BYOK Provider 设置页：OpenAI 兼容 base_url + key 的本地配置（key 脱敏存储）、连通性测试（列模型）。
- 投递追踪模型硬化：新增「状态原因」列；终态（已挂/已放弃）不可回退阶段；同公司+岗位去重拦截；进入终态强制填写原因。CLI、API、前端三端同一套校验（`tools/tracker.py` 为单一事实源）。
- 领域插件体系：`template/profiles/<domain>/` 可插拔领域目录，新增领域不改代码；以无关领域（software-backend）验证通过。
- 六大模块模板：`template/workspace/` 提供全部模块的填写引导骨架。
- Electron 桌面壳：主进程探测打包后端（优先）或本机 Python（回退）→ 拉起后端 → 轮询就绪 → 开窗加载 → 退出时杀进程树；前端静态产物由后端同源托管。
- PyInstaller 后端打包（onedir）：独立 exe 免 Python 环境；`scripts/build_backend_exe.ps1` 一键构建；`pathres.py` 处理打包/源码双模式路径与可写数据目录回退（便携模式 → 系统用户目录）。
- 追踪增强：看板统计卡、漏斗柱、方向、批次可点击下钻（跳追踪表并预置筛选）；状态变更时间线（每次字段变更入账独立 `history.csv`，追踪表行内展开查看）；阶段停留天数（超阈值高亮）；静默提醒（非终态记录长期无进展在看板独立成卡，默认阈值 14 天）；关键字搜索（公司/岗位/备注）与排序（下次动作日期/评分/停留天数）；下次动作日期就地编辑与看板待办一键顺延 7 天。时间线读写与停留天数计算集中于 `tools/tracker.py`，CLI 与 Web 共用。
- 简历数据驱动「标准版式」：`tools/resume_build.py` 新增 `render` 子命令，由 `02_简历工坊/source/resume_<版本>.json` + 内置 HTML 模板渲染出 A4 PDF；`render` 额外断言 A4 纸型（防模板漏 `@page` 导致 Letter）。无子命令时仍直接打印手写 HTML，两条路径并存。
- 简历工坊页（Web）：左结构化表单、右 A4 实时预览，编辑即时写回 JSON；生成 PDF 后回显 ATS 三项与纸型校验结果；含防超页护栏（超一页时提示并禁用生成）与诚实红线常驻提示。新增 `/api/resume*` 路由。
- 简历工坊信息架构调整（双模式）：「标准版式」= 数据驱动编辑，支持在页面上直接新建版本（不再要求手工放 JSON）；「高级模板」= 手写 HTML 精排版的只读浏览与一键生成，文件能力自素材库迁入（`/api/resume/templates*`）。素材库只保留事实库，消除同名「简历工坊」的混淆。

### Changed

- 项目更名：由「秋招工作台」统一为「求职工作台」（显示名与文档；目录名与历史归档不变）。
- 架构重构：由单用户个人工具重构为通用工作台——工具层（tools/skills）/ 领域插件层（template/profiles）/ 用户数据层（personal）三层单向分离。

### Fixed

- 目录重组后 68 处内部路径引用断链。
- 链接修复脚本深度补偿不幂等、归档说明被误改。
- 素材库页面偶发黑屏：hash 路由 + ErrorBoundary 兜底。
- 一键启动脚本的三层路径定位缺陷（`$PSScriptRoot` 空值、路径层级等）。
- 岗位列表页评分一致性问题。
- 岗位详情页展开逻辑的空值隐患（`tsc -b` 构建期暴露）。
- 数据目录根语义错误（工作区根误用工作区目录本身，导致默认工作区标识失效）。
- 工作区切换在 reload 后失效（未持久化选择，reload 丢回默认工作区）：改为 localStorage 记忆上次选择，重载后优先恢复。
- 首屏工作区竞态（内容区在 `listWorkspaces` 设好全局工作区前 mount，切到非默认工作区 reload 会先渲染一次默认数据）：以"工作区就绪后才渲染内容 + 工作区作 key 强制重挂"修复。
- 生成 PDF 时后台读 stderr 触发 `UnicodeDecodeError`（Windows 下以 locale/GBK 解码 Chrome 输出）：改为丢弃浏览器输出，只以 PDF 是否生成判成败。
- `verify_pdf` 的 ATS 关键事实清单依赖模块级全局，Web 并发下会互相覆盖：新增 `facts_file` 显式参数，Web 场景必须传入。

[Unreleased]: https://keepachangelog.com/zh-CN/1.1.0/
