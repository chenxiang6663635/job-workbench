# jobws-mcp

求职工作台（job-workbench）的 MCP 服务。本地优先：读本机工作区的
Markdown / CSV，不出网。**默认只读**；写入走**两段式**——`preview_*` 只给
令牌与差异（不落盘），用户确认后 `apply_approval` 才真正写入。

## 提供的工具

| 工具 | 作用 |
|---|---|
| `list_applications` | 投递记录列表（只读；按阶段 / 关键词过滤，按「下次动作日期」排序，终态沉底） |
| `list_jobs` | 岗位池列表（只读；公司、岗位、解析卡评分、投递状态三态） |
| `dashboard_summary` | 看板摘要（只读；漏斗、近 7 天待办、已过截止、静默提醒、待推进、转化率与失败归因） |
| `preview_add_application` | 预览新增一条投递记录（**不写入**；返回一次性令牌与 diff） |
| `preview_import_applications` | 预览按 CSV 批量导入（**不写入**；有错误行时不给令牌） |
| `preview_update_application` | 预览更新一条投递记录（**不写入**；只列要改的字段。可更新字段与新增同族） |
| `apply_approval` | 凭令牌执行已确认的写入（两段式第二步；令牌一次性、10 分钟、绑定工作区） |
| `list_interviews` | 面试记录列表（只读；按关联记录 / 结果过滤。复盘字段要 `verbose=True`） |
| `score_jd` | 读 JD 解析卡给出评分与档位（只读；四维之和必须等于总分才给档位） |
| `list_questions` | 题库列表（只读；按领域 / 科目 / 状态过滤，口径与 `bank list` 同源） |
| `preview_add_interview` | 预览新增一条面试记录（**不写入**；返回令牌与 diff） |
| `preview_update_interview` | 预览更新一条面试记录（**不写入**；只列要改的字段） |
| `preview_add_question` | 预览新增一道题库题目（**不写入**） |
| `preview_import_questions` | 预览从 `03_面试准备` 导入题目（**不写入**） |

工具一律**追加在注册末尾**（顺序稳定 → 宿主的工具描述缓存不失效）；需要完整字段
的列表用 `verbose=True`，列表类默认只给精简列。

拒绝是**可程序化区分**的：`apply_approval` 失败时返回稳定 `code`——`not_found`
（不存在 / 已用过，含重放）、`expired`、`fingerprint`（载荷被改过）、`binding`
（工作区不符）等；宿主按 code 分支，不要解析中文文案。

## 只读资源与提示模板（批 8：按需读取）

- **资源**（list 只列清单，read 才取内容；**不要全量预载**——那既贵又慢）：
  - 固定 URI 三个：`jobws://workspace/applications`（投递记录）、
    `jobws://workspace/jobs`（岗位池）、`jobws://workspace/dashboard`（看板摘要）；
  - 岗位正文模板两个（2026-09-18 补）：`jobws://job/<目录名>/jd`（JD 原文）、
    `jobws://job/<目录名>/card`（解析卡正文）——`<目录名>` 是**单个目录名**
    （如 `云帆_后端`，不含斜杠）。正文只给 Markdown / 纯文本（简历 PDF 等二进制
    与凭证文件**没有入口**），单条上限 20 KB、超出截断并注明完整路径。
- **提示模板**：`review_jd`（评估 JD）、`generate_application_pack`（投递包）、
  `interview_review`（面试复盘）、`today_todos`（今日待办）——只做参数化组装，
  准则在 `skills/jwb-*` 里，不在这里复制第二份。提示里提到的数据都指向上面真能
  读到的资源或工具（需要完整字段的列表用 `verbose=True`）；MCP 面没有的能力
  （如阶段时间线）提示会明说"请在界面查看"，不诱导模型编造。

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

需要 Python **3.12+**（与领域包 `jobws-core` 同一条基线；此前写 3.10+ 是因为领域层还没搬完）。两个环境独立是**职责分层**
（可选组件 vs 应用本体），不是依赖互斥——历史上「主干 pydantic <2.10 与 SDK >=2.12
互斥」的前提已随 3.12 基线消失（交集 `>=2.12,<2.14`，同环境实测全过；详见
`mcp/pyproject.toml` 的说明段）。

```bash
pip install -e ./mcp
jobws-mcp --workspace personal        # 工作区名，或绝对路径
```

**装上就能用**（2026-09-19 PR-B）：领域层**全部**在 `packages/jobws-core` 里（写入原语、
文件锁、`pathres`、`tracker`、`approval`、`jd_score` / `report` / `question_bank` 等）。
本包原先那段「sys.path 注入 + `JOBWS_REPO_ROOT` 推导 + 找不到仓库就 ImportError」的硬闸
已**整段删除**——装在哪都行，不需要仓库在侧。

两处说明：

- **安装顺序**：`jobws-core` **不在 PyPI**（它是本仓的包），所以要先装本地包：

  ```bash
  uv pip install packages/jobws-core   # 先
  uv pip install ./mcp                 # 后
  ```

- **两个操作仍需要仓库**：`prep.toggle`（笔记勾选框写回）与 `init`（初始化工作区）的实现
  模块按设计留仓，登记发生在仓库的 `tools/approval.py`。独立安装下调它们会得到
  `unknown_operation`——**稳定错误码**，明确表示"这个操作需要仓库在侧"，不是崩溃。
  其余十个写操作（`track.*` / `talk.add` / `mail.add` / `interview.*` / `question.*`）
  装包即用。

注：两个包现在**同一条基线**：Python **3.12+**（`jobws-mcp` 此前写 3.10+ 是因为领域层
还没搬完；现在它硬依赖领域包，版本线随之对齐）。

## 宿主配置示例

**键名按宿主各不相同，别照抄**（本机实测 2026-09-17；混用会静默不生效——
配置看起来没问题，宿主却根本不会拉起这个服务）：

**Claude Code / Claude Desktop / CodeBuddy / Gemini CLI** —— `mcpServers`：

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

**Codex CLI** —— `~/.codex/config.toml` 的 `[mcp_servers.*]`：

```toml
[mcp_servers.jobws]
command = "jobws-mcp"
args = ["--workspace", "personal"]
```

**VS Code** —— `.vscode/mcp.json` 的 `servers`：

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

完整接入说明（含故障排查与两段式写入的用法）见 `docs/mcp-integration.md`。

## 工作区解析

优先级：`--workspace` > 环境变量 `JOBWS_WORKSPACE` > 默认工作区（受 `JOBWS_DATA_DIR` 影响）。

- 相对工作区名按**数据根**解析（本模块有意只认这一个根、比后端更严；打包形态下
  数据根是系统用户目录，那里才是用户数据真正所在。后端 `?ws=` 自 2026-09-16 起为
  「数据根优先 + 应用根兜底」，可达集合更大）。
- 解析结果**必须**落在**可写数据根**之内（2026-09-19 PR-B 起只剩这一个根：独立安装下没有「应用根」这个概念）：宿主可能由模型代传参数，少了这道
  检查等于给出任意目录的读取能力，所以越界一律拒绝而不是警告。比对前会 `realpath`
  （符号链接会读穿），也不允许把根本身当工作区。

## 测试

```bash
python -m pytest mcp/tests -q
```

`test_tools.py` 不依赖 MCP SDK（造真实工作区跑口径）；`test_stdio_smoke.py` 需要 SDK，
未安装时自动跳过——CI 由独立的 3.12 job 执行。
