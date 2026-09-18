# 把工作台接进 AI 宿主（MCP）

工作台除了命令行与桌面界面，还带一个 **MCP 服务**（`jobws-mcp`）：接进支持 MCP 的
AI 宿主之后，AI 就能读你的投递记录、岗位池与看板，并在**你确认之后**写入。

数据始终在你的机器上：MCP 服务走 stdio，只读写本地工作区，不联网、不上传。

> 四个入口（命令行 / AI 宿主 / 编辑器插件 / 桌面界面）各能做什么，见
> [`four-ends.md`](four-ends.md)（自动生成的能力对照表）。

## 一、安装

需要 Python 3.10+（MCP SDK 的要求；工作台后端基线是 3.12）。

```bash
pip install -e ./mcp
jobws-mcp --workspace personal          # 工作区名，或绝对路径
```

**仍需要仓库在侧，但原因变了**（2026-09-17 更新）：领域层已开始包化——写入原语与
文件锁进了 `packages/jobws-core`（`pip install -e packages/jobws-core`，装上就有、
wheel 也拿得到）；但**领域层主体**（`tracker` / `report` / `jd_score` 等）还在
`tools/` 下，要等下一批才搬进包。所以在那之前，MCP 仍需要能看到仓库：用 editable
安装最省事（`pip install -e ./mcp`，MCP 与仓库同处一处），或装成 wheel 后用环境
变量指到仓库根：

```bash
JOBWS_REPO_ROOT=/path/to/job-workbench jobws-mcp --workspace personal
```

自检：先不带宿主直接跑一次 `jobws-mcp --help`，能打印帮助就说明命令与环境没问题
（该进程会等 stdin，用 Ctrl+C 退出即可）。

## 二、接进宿主（三种配置形态）

**键名按宿主不同，混用会静默不生效**——配置看起来没问题，宿主却根本不会拉起服务。

### Claude Code / Claude Desktop / CodeBuddy / Gemini CLI —— `mcpServers`

```json
{
  "mcpServers": {
    "jobws": {
      "command": "jobws-mcp",
      "args": ["--workspace", "personal"]
    }
  }
}
```

（各宿主的配置文件位置不同：Claude Code 用项目级/用户级配置，CodeBuddy 用
`~/.codebuddy/mcp.json`，Gemini CLI 用 `~/.gemini/.../mcp_config.json`——位置按宿主
文档填，键名照上面。）

### Codex CLI —— `~/.codex/config.toml`

```toml
[mcp_servers.jobws]
command = "jobws-mcp"
args = ["--workspace", "personal"]
```

### VS Code —— `.vscode/mcp.json`

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

## 三、工作区解析

优先级：`--workspace` > 环境变量 `JOBWS_WORKSPACE` > 默认工作区（受 `JOBWS_DATA_DIR` 影响）。

- 相对工作区名按**数据根**解析；解析结果必须落在「应用根」或「可写数据根」之内。
- **越界一律拒绝**（不是警告）：宿主可能由模型代传参数，少了这道检查等于给出任意
  目录的读写能力。比对前会 `realpath`（符号链接会读穿），也不允许把根本身当工作区。

## 四、AI 能做什么

**只读**：投递记录列表、岗位池与解析卡评分、看板摘要（漏斗 / 待办 / 逾期 / 静默 /
转化率）、面试记录、题库、JD 解析卡评分与差距。

**写入（一律两段式）**：新增与批量导入投递记录、更新投递记录、新增与更新面试记录、
新增题目、从 `03_面试准备` 导入题目。

AI 侧的正确用法是三步，工具的说明文字里也写了：

1. 调 `preview_*` 拿到**令牌 + 差异表**（此时**没有任何落盘**）；
2. 把差异表展示给你看；
3. 你点头之后，AI 才用**同一个令牌**调 `apply_approval` 落盘。

令牌**一次性、默认 10 分钟有效、绑定该工作区**——重放、过期、来自别的工作区、
载荷被改过的令牌都会被拒绝，拒绝时返回稳定的错误标识（`not_found` / `expired` /
`binding` / `fingerprint` / `conflict` 等），AI 据此决定要不要重新预览。

为什么要在协议上留痕而不是靠提示词：宿主把工具当手用，模型看一遍摘要就调落盘的
成本几乎为零——"给用户看过"必须是协议的一部分。

## 五、故障排查

| 现象 | 原因与处理 |
|---|---|
| 宿主里看不到这台服务 | 键名写错了（见第二节的三种形态）；或 `command` 不在 PATH 里——先用绝对路径试 |
| 工具调用报工作区越界 | `--workspace` 指向了允许根之外；改用数据根下的工作区名 |
| 落盘被拒且提示过期 | 令牌超过 10 分钟或已用过——重新 `preview_*` 再确认 |
| 落盘被拒且提示指纹不符 | 令牌记录被改过（极少见）；重新预览 |
| 只看得到数据、写不进去 | 这是设计：写入必须由模型先预览、你确认后落盘 |
| 服务启动报找不到领域函数 | 没以 editable 安装或仓库不在侧——见第一节 |

## 六、相关文档

- [`../mcp/README.md`](../mcp/README.md)：MCP 包自身的设计说明与工具清单
- [`four-ends.md`](four-ends.md)：四个入口的能力对照（含"哪端不提供、为什么"）
- [`usage-guide.zh-CN.md`](usage-guide.zh-CN.md)：工作台整体用法
