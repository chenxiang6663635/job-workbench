# jobws-mcp

求职工作台（job-workbench）的**只读** MCP 服务。本地优先：只读写本机工作区的
Markdown / CSV，不出网、不写数据。写入能力属于后续批次（写入预览 + 确认令牌）。

## 提供的工具

| 工具 | 作用 |
|---|---|
| `list_applications` | 投递记录列表（按阶段 / 关键词过滤，按「下次动作日期」排序，终态沉底） |
| `list_jobs` | 岗位池列表（公司、岗位、解析卡评分、投递状态三态） |
| `dashboard_summary` | 看板摘要（漏斗、近 7 天待办、已过截止、静默提醒、待推进、转化率与失败归因） |

三个工具的口径都与 CLI / Web **同源**：漏斗与待办照抄后端看板，评分照抄
`jd_score`，排序照抄 `tracker.sort_key`。各写一套判据迟早给出互相矛盾的结论。

## 安装与运行

需要 Python 3.10+（MCP SDK 的要求；主干后端仍可保持 3.8，两者环境独立）。

```bash
pip install -e ./mcp
jobws-mcp --workspace personal        # 工作区名，或绝对路径
```

免安装运行（分发形态）：

```bash
uvx --from ./mcp jobws-mcp --workspace personal
```

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

优先级：`--workspace` > 环境变量 `JOBWS_WORKSPACE` > 默认工作区（受
`JOBWS_DATA_DIR` 影响）。

解析结果**必须**落在「应用根」或「可写数据根」之内：宿主可能由模型代传参数，
少了这道检查等于给出任意目录的读取能力，所以越界一律拒绝而不是警告。

## 测试

```bash
python -m pytest mcp/tests -q     # 需要 3.10+（mcp SDK）；CI 有独立的 3.12 job
```
