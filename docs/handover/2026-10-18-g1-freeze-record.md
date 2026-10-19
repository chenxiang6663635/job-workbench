# G1 冻结记录（候选 `b301687`，2026-10-19 第二次刷新）

> **性质**：**提案**。G1「冻结」= ①停止向 `main` 合并功能改动 ②钉死候选 SHA
> ③转入 G2/G3 真机验收。本文件供用户批准后生效；未批准前不算冻结。
>
> 冻结的意义不是"做完了一切"，而是**"凡是要进这一版的，都已经在了"**——
> 之后只允许修复 G2/G3 暴露的阻断问题。

## 一、候选与范围

| 项 | 值 |
|---|---|
| 候选 SHA | `b301687`（本记录合并后 `main` 会再前进一格；差异**仅本文件**，代码零改动）→ **批准时以当时的 `main` 为正式钉死点** |
| 基线 | `v26.10.0`（2026-10-06） |
| 区间提交数 | **60**，**全部来自 PR**（直接推送 0 个——可复核：`git log --pretty=%s v26.10.0..HEAD` 每条都以 `(#N)` 结尾） |
| 版本号 | 仍 `26.10.0`（取号在 G3 落章时做，届时元数据变更后成品须重建重验） |

## 二、本版并入（按主题分组）

**安全与数据根**：#300（岗位读取三级归属 + 字节有界读）、#302（已生效迁移禁止指针式回滚）、
#305（反向迁移如实说明）、#307/#308（领域层读取与追加边界收口）、#311/#312（根解析按显式选择
分流，不再跨根回退）、#313/#314（CLI 默认工作区跟随持久化数据根）、#326（JD 抓取出网守卫）。

**门禁与 CI**：#294/#295（CodeQL 接入与站收尾）、#306（依赖审计两条命令都执行）、
#316（S4 门禁升级记录）、#317（CodeQL 不再按路径跳过 PR）、#327/#328（CodeQL 债务姿态与机制实测）。

**桶一（取号前小修）**：#287 —— 评分档位缝隙、插件回退、工作区校验、令牌簿记、`history.csv` 双保险。

**桶二（积累期主线）**：#288（测试盲区）、#289（读放大 + xdist，全量 45s→19s）、
#290（重复实现收编 + `tools_readonly` 拆分）。

**前端体验与可访问性**：#273（笔记搜索状态行）、#291（路由懒加载 / 长表窗口化 / 数据根重选入口 /
笔记插图端点）、#292（i18n 长尾 + skip-link）、#293（英文对照文档四件）、#303（笔记互链返回栈）。

**DSH 接入**：#281（npm 包化）、#282（随包 `jobws-mcp.exe`）、#283（一键安装 + 幂等迁移）、
#284（版本兼容声明与准入实测）、#285（parity 矩阵收口）、#286（接入页与支持策略）+ #324（exe 重建到 17 工具）。

**E 批筛选校准**：#318（ADR 三点决策）、#323（实现，四端同源）。

**设置页**：#280（凭据「清除即删」）。

**发布记录与文档**：#275–#279、#310（交接包纳管）。

## 三、明确不做 / 顺延（附理由，避免"以为漏了"）

| 项 | 处理 | 理由 |
|---|---|---|
| `26.10.1` hotfix | **不做** | 风险矩阵裁决：四条风险共同前提都是非默认布局、无实际事故；证据落在第二档（tag 树实测完成、安装包未复核），签署条件已写 4 条 |
| E-03「放掉记账」写入口 | 顺延 | 本批只读；写入口需单独立项（设计文档 §四 反目标） |
| CodeQL 存量（184 条） | 12 条非路径告警已根因修复；182 条 path-injection 已分诊、不逐条改 | #331–#335 修完 ReDoS / URL 判定 / stack-trace（194→184，实测关闭）；#338 分诊；#339 实测发现 `resolve_profile` 的 domain 可穿越并修掉 |
| #325（#194 修复） | **已合并**（`60a366d`，2026-10-19；#194 告警自动转 `fixed`） | 已补三处链接边界负向测试；CodeQL 对该 PR 报 **0 new alerts**（`unsafe_links` 被识别为 SafeAccessCheck），不再需要 dismissal 或 QL 包 |
| P1-B ②③（反向迁移） | 不做，如实说明 | #305：技术上当前不可行，写在文档里而不是假装有 |
| 全站 WCAG AA 专项 | 延后 | 按审计建议：避免 a11y 收口无限扩张（最小键盘可达性已闭环） |

## 四、验证读数（2026-10-18 当前 main）

| 项 | 读数 |
|---|---|
| 主套件 | **2031 passed / 37 skipped**（20.0s，`-n 4`；+4 skip 是本机 Windows 建不了文件符号链接，CI ubuntu 上真实执行，那边读到 **2055 passed / 12 skipped**） |
| MCP 套件 | **101 passed / 10 skipped**（7.5s，MCP venv） |
| 扫描器 7 项 | i18n / size / four-ends / legacy-imports / ui-tokens / themes / domains **全部通过** |
| MCP 工具面 | **17 个**（冒烟钉住数量 + 末位 `score_calibration` + 真调两个后补工具） |
| 随包 exe | `prebuilds.json` **211 条**，逐文件 sha256 复核 0 不符 / 0 多余 |
| 门禁 | S1–S4 生效中；本区间 0 次直接推送 main |

## 五、冻结后要你执行的三件事（G2/G3，须在场）

1. **干净环境构建**（从候选 SHA 全新构建后端/前端/桌面端，确认无本地残留依赖）；
2. **Windows 真机安装 / 卸载 / 升级**（本机两次被 UAC 交互阻断，无法无交互完成）；
3. **`v26.10.0` 隔离安装探针**三场景 —— **P2 错根写** / **S2 越界** / **env→不存在的根**
   （用临时目录、不碰真实数据）；结果回填风险矩阵，其裁决由"暂定"转"正式"；
4. **回滚演练**（安装 → 回滚到上一版 → 数据完好）。

## 六、挂起项与它的代价（说明为什么冻结不受影响）

**#325（CodeQL #194 命令行注入修复）——已合并（2026-10-19，`60a366d`）**。合并后实测：`#194` 告警状态转 **`fixed`**，`py/command-line-injection` 归零；`tools/pdf_print.py` 在 main 上产生 **0 条新告警**。以下为合并前的挂起经过，保留备查：分支 `fix/command-line-injection` 除 CodeQL 门禁外全绿
（2006 passed 时的那次运行），PR 分析里 `py/command-line-injection` **已 0 条**——说明修复有效；
但新文件的 4 处"写用户自选输出路径"被判 `py/path-injection`（high），门禁按"新增"拦下。

- **不做 `paths-ignore`**：它关掉的是该文件**全部**规则，包括刚修好的那条；
- **不做 QL 概念包**：Python 的扩展点是 `Path::SafeAccessCheck::Range`（带状态机），不是加个类名；
  且需 fork/打补丁标准库包，长期维护负担 > 收益；
- **风险现状**：`tools/pdf_print.py` 的 argv 只剩候选表字面量与临时固定名，**当前不可利用**。

→ 因此它**不构成冻结阻断**：主干上不存在这个缺陷（缺陷只在旧版 exe 的构建里，而 exe 已重建）。

## 六之二、CodeQL 现状（2026-10-19）

| 项 | 状态 |
|---|---|
| open 告警总数 | **184**（基线 194；12 条非路径告警已根因修复并实测关闭） |
| `py/stack-trace-exposure` | **0**（5 条全收，#332–#335；三级源头：路由层 / `dataroot_migrate` / `dataroot_semantics`） |
| `py/polynomial-redos` | **0**（3 条；20k 空白 3.78s → 0.11s，性能用例钉住） |
| URL 子串判定（py+js） | **0**（2 条；改主机名相等，收进 `outbound.host_is`） |
| `py/full-ssrf` #2 | 代码已修并合并（#326）；告警 open（不认自定义校验器） |
| `py/command-line-injection` #194 | **已关闭（`fixed`）**——#325 于 2026-10-19 合并后自动置 fixed |
| `py/path-injection` | 182 条存量；已分诊（`report_path_injection_triage.md`），按策略不逐条改 |

**#325 为什么从 BLOCKED 变成 CLEAR**（实测确认，非偶然）：新增的
`pdf_print.unsafe_links()` 在**任何文件操作之前**逐个检查输入路径（`islink` / `isjunction` /
递归 `os.walk`），命中即 `return False` —— CodeQL 的 path-injection 有 `SafeAccessCheck`
概念，把它识别成合法 barrier。为排除"分析没覆盖到"的假阴性，特意**碰了一次该文件**
强制重新分析：仍是 `0 new alerts`。这是结构性修复被识别，不是抑制。

**合并后核对（已完成）**：open 告警 184 → **182**（`py/path-injection` 182→181、`py/command-line-injection` 1→0）；main 上 `tools/pdf_print.py` **0 条新告警**。

## 七、复现命令（任何人接手都能重跑）

```powershell
git checkout cd464e0
python -m pytest tests/ -q -p no:cacheprovider -n 4        # 2001 passed
D:\tools\venvs\jobws-mcp\Scripts\python.exe -m pytest mcp/tests -q   # 101 passed
python tools/jobws.py lint i18n,size,four-ends,legacy-imports,ui-tokens,themes,domains
D:\tools\venvs\jobws-mcp\Scripts\python.exe scripts\smoke_mcp_exe.py # 17 工具 + SMOKE OK
```
