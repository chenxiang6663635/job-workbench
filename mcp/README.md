# jobws-mcp

求职工作台（job-workbench）的**只读** MCP 服务。本地优先：只读本机工作区的
Markdown / CSV，不出网、不写数据。写入能力属于后续批次（写入预览 + 确认令牌）。

## 提供的工具

| 工具 | 作用 |
|---|---|
| `list_applications` | 投递记录列表（按阶段 / 关键词过滤，按「下次动作日期」排序，终态沉底） |
| `list_jobs` | 岗位池列表（公司、岗位、解析卡评分、投递状态三态） |
| `dashboard_summary` | 看板摘要（漏斗、近 7 天待办、已过截止、静默提醒、待推进、转化率与失败归因） |

口径与 CLI / 网页端**同源**：终态、待办（下次动作日期优先于截止日期）、逾期（只看
「待投」）、静默（`tracker.stale_days`）、健康度（`tracker.health_score`）照搬后端看板；
评分照搬 `jd_score`（含「四维之和必须等于总分」的自洽校验）；排序照搬 `tracker.sort_key`；
岗位池的**匹配键只用目录名**（卡片里的公司名常更详细，当键会与追踪表系统性失配）。

**两处有意与后端不同的地方**（都写在代码注释里）：

- `list_applications` 的 `keyword` 同时匹配公司与岗位，CLI 的 `filter_rows` 只匹配公司——
  MCP 侧由宿主代传，模糊一点更好用。
- `dashboard_summary` 是看板的**子集**：不含 `byBatch`、`staleDays`、`unappliedHigh`、
  `scoreByState`、`stay` 与 `failureClusters`——摘要服务追求的是「一眼看清」，不是搬家。

## 安装与运行

需要 Python 3.10+（MCP SDK 的要求；主干后端基线 3.12，两者环境独立——pydantic 依赖集互斥）。

```bash
pip install -e ./mcp
jobws-mcp --workspace personal        # 工作区名，或绝对路径
```

**当前形态需要仓库在侧**：领域函数（`tracker` / `report` / `jd_score`）还在 `tools/` 下，
没抽成可安装的包（那是 B8 的活），所以本包暂时以 editable 方式与仓库共存；装成 wheel 会
拿不到领域层。仓库不在默认位置时，用环境变量指过去：

```bash
JOBWS_REPO_ROOT=/path/to/job-workbench jobws-mcp --workspace personal
```

等 B8 把领域层抽出成可安装的包之后，`uvx --from ./mcp jobws-mcp` 这类完全独立的分发才成立。

## 宿主配置示例

```json
{
  "servers": {
    "jobws": {
      "type": "stdio",
      "command": "jobws-mcp",
      "args": ["--workspace", "personal"]
    }
  }
}
```

## 工作区解析

优先级：`--workspace` > 环境变量 `JOBWS_WORKSPACE` > 默认工作区（受 `JOBWS_DATA_DIR` 影响）。

- 相对工作区名按**数据根**解析（源码/便携形态下数据根就是应用根，与后端 `?ws=` 一致；
  打包形态下数据根是系统用户目录，那里才是用户数据真正所在）。
- 解析结果**必须**落在「应用根」或「可写数据根」之内：宿主可能由模型代传参数，少了这道
  检查等于给出任意目录的读取能力，所以越界一律拒绝而不是警告。比对前会 `realpath`
  （符号链接会读穿），也不允许把根本身当工作区。

## 测试

```bash
python -m pytest mcp/tests -q
```

`test_tools.py` 不依赖 MCP SDK（造真实工作区跑口径）；`test_stdio_smoke.py` 需要 SDK，
未安装时自动跳过——CI 由独立的 3.12 job 执行。
