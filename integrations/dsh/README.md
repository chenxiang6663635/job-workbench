# job-workbench × DeepSeek Harness（DSH）

把求职工作台接进 DSH 宿主：**MCP 工具面**（15 个工具，两段式写入）+ **9 个 `jwb-*` 技能**。
本目录是「本机自用」形态的装配说明（第一阶段）；对外分发物（bundle 包、manifest、版本兼容）
属第二阶段，本目录只预留接口与约束。

实测环境（2026-10-05）：DSH `D:\tools\dsh`（`@deepseek-ai/*` 全家桶 0.2.0-rc.2）；
`jobws-mcp` 走专用 venv `D:\tools\venvs\jobws-mcp`（editable 指向本仓库）。

## 一、安装（三件，可分开用）

### 1. MCP 接线 —— `profile.patch.yml`

把 `- insert:` 块放进目标 profile。两种用法：

```powershell
# 临时叠加（不改任何 profile，一次启动即止）：
dsh headless --patch D:\tools\autumn-recruit-workbench\integrations\dsh\profile.patch.yml "你好"

# 持久接入：把 insert 块复制进 <DSH_HOME>/profiles/<profile>/cordis.patch.yml（追加到数组）
```

**数据根刻意不写进配置**（数据根 spec 决策 1）：`jobws-mcp` 自己读工作台的持久化选择与
B3 默认；`config.env.JOBWS_DATA_DIR` 只作应急覆盖——写死它会制造第二个事实源。

### 2. 可选：`jobws` preset —— `preset.yml`

preset = 声明式选择**工具集 / 提示词分节 / 技能**（`@deepseek-ai/dsh-agent-preset` 实例；
registry 默认仍是出厂 `standard`，新增实例只是多一个可选项）。装配方式同上（insert 块进
`cordis.patch.yml` 或 `--patch` 叠加）；会话里切到 preset `jobws` 后生效。

### 3. 技能

9 个 `jwb-*` 技能的真源在本仓库 `skills/`。DSH 的技能发现根（官方 rank 表）：

| rank | 来源 | 路径 |
|---|---|---|
| 100 | project-dsh | `<项目根>/.dsh/skills` |
| 200 | project-agents | `<项目根>/.agents/skills` |
| 300 | custom | `skill-filesystem` 的 `customSkillDirs` 配置 |
| 400 | user-dsh | `~/.dsh/skills`（跳过 `.system`） |
| 500 | user-agents | `~/.agents/skills` |

项目根 = 最近含 `.git` 的祖先。**在仓库根启动 DSH 时技能天然可见**（`install_skills.py`
已装 `.agents/skills`）；无仓库形态装用户级：

```powershell
python tools\jobws.py skills install          # 全部宿主落点一次同步
# 或无仓库时手动：把 skills/jwb-* 复制到 C:\Users\<你>\.agents\skills\
```

## 二、升级

```powershell
git pull
python tools\jobws.py skills install          # 技能有改动时重跑（拷贝不自动同步）
```

- MCP 侧是 **editable venv**（指向本仓库 `mcp/` 与 `packages/jobws-core`）——改代码即生效，
  无需重装；装配文件（patch/preset）本身无版本号。
- 升级后核对：`dsh headless --patch <profile.patch.yml> "..."` 无
  `entry did not activate` 警告即接线完好。

## 三、卸载与回滚

- **临时叠加**（`--patch`）：进程退出即无痕，无需卸载。
- **持久接入**：从 `cordis.patch.yml` 删除对应的 `insert` 条目（`mcp-jobws` /
  `preset-jobws`），重跑 DSH 即回到原状；技能则从落点目录删除 `jwb-*`。
- **数据零影响**：本目录的装配只加「读取与调用入口」，不迁移、不写工作区；卸载不动数据。
- 回滚演练（接入前）：`Get-FileHash <profile>\package.json, <profile>\cordis.patch.yml`
  留基线；改后核对哈希只在预期文件上变化。

## 四、验收清单（每个接触 DSH 的改动跑一遍）

1. **合成**：`dsh headless --patch <本目录 profile.patch.yml> --dump-config` → 输出树里出现
   `mcp-jobws` 条目；无 `entry ... not found` 警告。
2. **激活**：`dsh headless --patch <...> --json "调用含 jobws 的信息工具，打印 dataRoot.state"`
   → NDJSON 事件流里有一条 `tool_call`（工具名形如 `mcp__jobws__jobws_info_<12位哈希>`）
   且 `tool_result` 的 `state` 与 `python tools/jobws.py doctor` 一致。
3. **spawn 计数**：stdio 协商会**先后起两个进程**（临时探针 + 服务进程）——健康检查 /
   重复进程检测必须把探针算进去，否则会误报「启动了两个 server」。
4. **两段式**（有写入的会话）：`preview_*` 之后**没有**落盘，出示 diff 并经用户确认后
   `apply_approval` 才写入（可在会话里对临时工作区演练）。
5. **preset**（装配了 preset.yml 时）：启动无 `entry did not activate` 警告；会话切到
   `jobws` preset 后 persona 语境生效。

## 五、已知边界（写清楚比含糊兜住更有用）

- **工具名会被宿主规范化**：`jobws.info` → `mcp__jobws__jobws_info_<12位哈希>`（点转下划线
  并加哈希后缀）。提示词 / 技能里**不要硬编码**宿主侧完整名——说「含 `jobws` 的工具」或
  按功能描述即可。
- **DSH 不支持 MCP 提示模板**（已实证）：四个工作流（JD 评估 / 投递包 / 面试复盘 / 今日待办）
  改由 `jwb-*` 技能与 `jobws` preset 承载；`mcp/prompts.py` 保留给支持提示模板的宿主。
- **headless 一次性 profile 无 `agentPresets` 服务**（2026-10-06 真机实证）：`dsh headless`
  下 `preset-jobws` 停在 pending（信息级优雅降级，非缺陷）——persona 前缀在 headless 会话里
  不生效；两段式纪律由 MCP 工具描述自描述生效。**preset 的生效面 = 桌面会话 / 设置里切换**。
- **MCP 看不到源码形态的应用根**（结构性盲区）：工具报「无歧义」不等于全机无歧义——
  详见 `docs/mcp-integration.md` §三。
- `failOnStartupError`：本机自用 `true`（起不来就响亮失败）；对外发布改 `false`（不连累
  宿主整机启动）。
- 第二阶段预留：MCP 可执行文件换随安装包分发的 `jobws-mcp.exe`（只改 `command` 一行）、
  bundle 包与 manifest、版本兼容声明。
