# 文档索引

按阅读顺序排列。不确定先看哪份时，从第一份开始。

## 先读这两份

| 文档 | 说明 |
|---|---|
| [`../README.md`](../README.md) | 项目主入口：定位、三层架构、快速开始、目录说明 |
| [`../web/README.md`](../web/README.md) | Web 界面怎么启动、三个页面、与 CLI 的关系 |

## 设计文档

| 文档 | 状态 | 说明 |
|---|---|---|
| [`specs/2026-08-30-general-workbench-design.md`](specs/2026-08-30-general-workbench-design.md) | **现行** | v2.0 通用工作台架构：三层分离、领域插件契约、脚本参数化、迁移映射 |
| [`specs/2026-08-30-web-prototype-design.md`](specs/2026-08-30-web-prototype-design.md) | **现行** | Web 界面层：架构、API 契约、数据契约、并发与安全、验证记录 |
| [`specs/2026-08-30-autumn-recruit-workbench-design.md`](specs/2026-08-30-autumn-recruit-workbench-design.md) | ⚠️ **已废弃** | v1.0 个人工具设计。目录结构已失效，**勿据此开发**。保留作评分框架的设计依据追溯 |

## 约定文件

| 文件 | 说明 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | AI 工作约定：三层架构铁律、通用/个人边界、工程约束、目录约定 |
| [`../template/AGENTS.example.md`](../template/AGENTS.example.md) | 候选人档案模板，含逐项填写说明与真实样例 |
| [`../template/workspace/README.md`](../template/workspace/README.md) | 六个模块的用途、填写顺序、关键纪律 |

## 领域插件

| 文件 | 说明 |
|---|---|
| [`../template/profiles/hvac-cooling/profile.md`](../template/profiles/hvac-cooling/profile.md) | 暖通制冷与数据中心冷却插件 |
| [`../template/profiles/software-backend/profile.md`](../template/profiles/software-backend/profile.md) | 软件后端与数据工程插件（用于验证跨领域可扩展性） |

新增领域只需新增一个插件目录，无需改代码，见通用设计文档第 5 节。

## 技能文件（工作流定义）

`../skills/` 下五个：`recruit-coach`（评分标准与红线）、`jd`、`apply`、`track`、`resume`。

这些既是 AI 可加载的技能，也是各工作流的规格说明——读它们等于读流程定义。

## 已归档代码

| 文件 | 说明 |
|---|---|
| [`deprecated/fix_links.py`](deprecated/fix_links.py) | 个人重组时用的一次性断链修复工具，已停用。保留作路径替换逻辑的参考 |
