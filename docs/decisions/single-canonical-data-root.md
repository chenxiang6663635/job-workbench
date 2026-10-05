# 决策：单一 canonical 数据根 + 历史工作区迁移

- 状态：已采纳（2026-10-04；spec：[`../specs/2026-10-04-single-canonical-data-root.md`](../specs/2026-10-04-single-canonical-data-root.md)）
- 相关：`support-and-compatibility.md`（兼容承诺措辞）、`data-flow-matrix.md`（数据位置）、`four-ends.md`（契约矩阵落点）、[`keep-writes-human-confirmed.md`](keep-writes-human-confirmed.md)（迁移复用「预览→确认」形状）、`docs/research/report_agent-integration.md`（宿主侧前置调研）

## 背景

产品有四个调用端（Web 后端 / CLI / 桌面端 / MCP），但「数据根落在哪」由各端自己决定传不传应用根：源码/CLI 形态非打包即走便携（**仓库即数据根**），打包形态与 MCP 则落到用户目录（`mcp/jobws_mcp/paths.py` 有意不传应用根——它可能装在任意 venv，没有「应用根」概念）。

后果已经真实发生过一次：`%APPDATA%\job-workbench\personal` 冻结在 2026-09-26，仓库 `personal/` 成为现役，两边在 105 个同路径文件上不同、各有独有文件。2026-10-04 的只读盘点确认**没有未合并的数据损失**（仅 AppData 侧 11 个文件全部有对应物或被更新版取代；唯一「同大小异内容」文件是已废止的旧口径数字）。

最危险的形态不是崩溃而是**「一切正常」**：开发后端活着时安装版复用 8765 看到最新数据；开发后端一退出，安装版自己拉起 frozen 后端，静默切到 09-26 的旧副本——没有错误、没有提示。

## 决策

1. **四端只经同一个解析器**；优先级 `JOBWS_DATA_DIR > 持久化选择 > legacy 默认`；**不新增** invocation 级覆盖；相对路径一律拒绝；env 遮蔽持久选择时四端可见告警。
2. **持久化选择落在 `<user_data_dir>/state/data-root.json`**：位置不依赖应用根（MCP 必须能读），控制面用 `state/` 而非 `config/`（后者已专指工作区领域配置）；原子写，并显式承认无 fsync 即无崩溃耐久性。
3. **三态 + 失效 fail-closed**：`ambiguous`（多候选：读允许+告警、写不硬禁、破坏性拒绝）/ `unavailable`（持久选择失效：读写全拒，`sys.dataRootUnavailable`，**禁止静默回落**）/ `uninitialized`（正常首启）。补救命令在三态下都可用。
4. **迁移 = 事务**：`plan → copy → verify → switch → done/failed`，switch 最后写；**copy-first / switch-second / delete-never**；按 `root_id` 幂等；无歧义自动、有歧义一键确认（复用预览→确认形状）。
5. **新装默认 = `<user_data_dir>/data`**，「非打包即便携」降级为显式选择——这是「无配置时四端同根」的前提。
6. **诊断对象单一化**（`ResolvedDataRootDiagnostic`）：CLI `jobws doctor` / API `/api/system/paths` / MCP `jobws.info` / 设置页只做 presenter。
7. **契约矩阵挂 `lint four-ends`**（`tools/check_four_ends.py` + `tools/four_ends_matrix.json`），保证四端解析同源可回归。

## 已评估的替代方案

- **只修 DSH（在宿主配置里钉死 `JOBWS_DATA_DIR`）**：只掩盖第五端，四端分歧继续存在，还会制造「产品设置指向 A、宿主配置指向 B」这第二个事实源。
- **先搬数据再修解析器**：缺解析器、可见性、歧义检测与回滚，搬数据本身风险更高；且下一次 `git clone` / 打包运行会立刻再分叉一次。
- **保留仓库为长期 canonical 位置**：checkout 生命周期风险不消失（`git clean -xfd` / 重克隆 / 目录改名都会连坐用户数据）。
- **持久化选择放在 `%APPDATA%\job-workbench\config\`**：与工作区领域 `config/` 撞词，违反「一个词一个含义」。
- **persisted 高于 env**：临时通道（测试隔离、spike、排障）失效，会造出「设了变量却不生效」这类新静默 bug。
- **立即把 Roaming 改 Local**：同时动「默认根」与「漫游语义」= 两次迁移；先登记为风险与复评条件。

## 复评条件

出现多机同步需求、用户报告 Roaming 同步冲突、或宿主对「数据根查询」提出正式接口需求时，重审决策 5 与 6（默认位置与漫游语义），以及诊断面的呈现方式。
