# 深度调研整合报告：job-workbench 该不该做「agent 插件 / 工具」

- 调研日期：2026-09-10
- 方式：4 个子代理并行调研（dsh 插件解剖 / agent-first 架构分层 / Python 工具的 agent 暴露 / 坑与反面证据）
- 工具限制说明：子代理**只有只读工具、没有写文件能力**，报告只在最终消息中回传且被调度器截断，故本文是**已到手的结论整合**；每条结论后面的「出处」是子代理给出的原始出处。截断后未能确认的部分集中在本文末尾「未确认清单」。
- 本文的用途：它是**「AI 助手是一等宿主、界面是可选查看器」这一方向判断的依据**。后续若质疑该方向，先读本文的结论摘要与反面证据，再读文末未确认清单——那里列的是**当时没能核实、因此不能拿来支撑决策**的部分。
- 阅读提示：这是调研整合，不是设计文档。设计取舍见 `docs/specs/` 下的现行文档。

## 0. 结论摘要（决策级）

1. **dsh 插件比我上一轮估的便宜得多**：最小 JS 外壳 **15–40 行**；甚至可以「零 JS 的技能包」或「<10 行的挂载插件 + SKILL.md」。业务逻辑可以完整留在 Python。
2. **但「多宿主支持」不该进路线图**：单人维护 × N 个宿主（各自格式、8KB 限制、TOML/Markdown、权限块差异）= N 倍成本；且 dsh 处于 developer preview，官方原文保留随时破坏兼容的权利。正确姿势：**一个主宿主 + 一个次宿主**，或**只做纯本地技能**。
3. **最高优先级的一处风险已经存在**：技能身份 = **目录名 = frontmatter `name`**，同名会**静默覆盖**（不是报错）。本仓现有 `apply / jd / resume / track / recruit-coach` **全是高概率通用名**——上架前必须加项目前缀（如 `jwb-resume`）。
4. **本仓已有一处真源漂移隐患**：`skills/` 是手工真源，同时存在 4 个镜像目录（`.codebuddy/ .claude/ .agents/ .codex/`），同一份 `SKILL.md` 有多份副本。参考做法是「源 → 生成 → 校验 → 安装」，且**生成产物禁止手改**。
5. **MCP 不是本项目的优先项**：对「纯本地数据 + 必须人工确认」的工具，主战场是 **CLI + Skill**；MCP 只在需要「结构化工具发现 + 长连接 + OAuth」时才值得。
6. **写入确认必须是硬闸门，不能靠提示词**：写操作默认 `--dry-run`，真实写入要 `--yes`（CLI）或 elicitation（MCP），并附 diff 预览。这正好与本项目已有的「批量导入确认门」「简历导入逐段核对」对齐。
7. **有一条权威的架构判据可以直接当验收标准**：`BuilderIO/agent-native` 的表述——「**如果去掉 UI 系统就崩，那说明 UI 才是核心，Agent 只是壳**」。

---

## 1. dsh 插件体系解剖（子代理 A）

### 1.1 插件是什么

- 插件 = 导出 `name` / `inject` / `apply(ctx)` 的 **ESM 模块**。
- 注册工具：`ctx.tools.register(defineTool({...}))`；挂载技能：`ctx.skills.registerProvider(...)`。
- 分发单位是 **bundle**：`package.json` 里声明 `dsh.bundle.patch → ./cordis.patch.yml`，该 YAML 用 `insert:` 列出要挂载的插件行（按包名引用已编译产物）。
- 四种安装：本地目录（`link:` pnpm 链接，**免构建**）/ npm（用预构建 `lib/`）/ tarball（`pnpm pack`，免构建）/ git（拉源码，**需作者提供 `prepare` + 用户显式 `allowBuilds` 授权**，供应链风险最高）。

### 1.2 工具注册的形状（可照抄）

```ts
export const name = 'my-tool'
export const inject = ['tools']
export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'read_file',                 // 模型可见名
    description: 'Read a file from disk.',
    parameters: { path: { type: 'string', required: true, description: 'Absolute path' } },
    output: { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] },
    async execute(args, exec) { /* 必须遵守 exec.signal */ },
  }))
}
```

硬性约定（子代理逐条给出）：注册是副作用式的（dispose 即注销）；`execute` **只返回规范 JSON 值**，不要返回内容块；必须遵守 `exec.signal`；`presentCall`/`presentResult` 必须是**纯函数**（不做 I/O、不读会话状态、不用时钟/随机数）；长任务走 `ctx.jobs.start(...)`。

### 1.3 市场与收录门槛（决定性）

- 社区有事实市场 **`dsh-market`**（DSH Settings 内一键安装/升级），精选列表 `awesome-dsh-plugin`。
- 收录硬门槛：**必须声明 `dsh.bundle`**（只声明 `dsh.client` 是最常见的被拒原因）+ 根目录有 `cordis.patch.yml` + 真实可用代码 + 仓库存在 ≥1 天 + 打 `dsh-plugin` topic。
- 分类共 **23 个**（`agi ui usage theme model identity session memory tools wsl browser vision voice docs skill workflow git notify dev security remote market fun`），且会随增长拆分。

### 1.4 关键判断题的答案

> **一个以 Python 为主的工具项目，要成为 dsh 插件，最少要写多少 JS/TS？**

**答：可以只做「技能 + 薄外壳」，最小 JS 外壳 15–40 行；甚至可以零 JS（纯技能包）或 <10 行的挂载插件，业务逻辑留给 Python。**

真实样本证明：`988hj7tczd-oss/dsh-modernize-code` = **CSS/TS 薄外壳 + 离线 Python 脚本**，外壳只做「解析路径 → `ctx.subprocess.spawn({argv:[python3, script, ...]})` → `JSON.parse(stdout)` → 渲染」。

### 1.5 风险

官方 README 原文（子代理引用）：**"THERE WILL BE COMPATIBILITY-BREAKING CHANGES"**；`@deepseek-ai/dsh-*` 全部是 `0.1.x-rc` 预发布版，API 未冻结。

---

## 2. Agent-first 架构分层实证（子代理 B）

### 2.1 四个仓库的共同骨架

**没有一个是「UI 优先」**，四个仓库都是同一范式：

```
源内容（Markdown/技能，手工真源）
   → 适配器（翻译成各宿主原生格式）
   → 生成产物（gitignore，禁止手改）
   → 安装器（软链到全局配置）
```

| 仓库 | 核心层 | 适配器层 | 壳层 | UI 可否删除 |
|---|---|---|---|---|
| `TencentCloudBase/CloudBase-AI-Toolkit` | `mcp/src/` + `config/source/`（手工真源） | `.generated/compat-config/`、镜像 skills、`plugin/`；`experts:sync`（rsync --delete → validate → register） | `dsh-plugin/`、CodeBuddy plugin、独立发布仓 | **可以（本就无 GUI）**；README FAQ：「Can I use this without a GUI IDE? **Yes.**」 |
| `sickn33/agentic-awesome-skills` | `tools/lib/aas-v1/`（暴露 `aas` CLI + `aas-mcp`）+ `schemas/` + `skills/` | `plugins/`、`scripts/`、`npm run validate/build` | `apps/web-app`（**只做发现/审查，不访问文件系统**） | **可以，且被明确定位为「辅助界面」** |
| `wshobson/agents` | 单一 Markdown 源（94 plugins，跨 5 宿主复用） | `tools/generate.py` + `adapters/` + `install_{copilot,opencode,antigravity}.py` | — | 无 UI |
| `googleworkspace/cli` | Rust CLI（`crates/`） | `.agent/ .claude/ .gemini/` + `gemini-extension.json` | — | 无 UI |

### 2.2 可照抄的流水线（`wshobson/agents`）

四段式：**generate → validate → install → collision-check**，配套抽象基类 `base.py`、能力矩阵 `capabilities.py`、每宿主独立适配器与安装器，并挂 CI 门禁。

**`check_agent_name_collisions.py --fail-on-duplicates` 具体在防 4 件事**（子代理逐条列出）：
1. 跨插件同名 agent → 静默互相覆盖；
2. 与宿主内置 agent 名冲突（Codex 的 `default` / `worker` / `explorer` 会被加 `__` 命名空间）；
3. 插件内 skill 与 command 同名 → 两条互相覆盖的条目；
4. **skill 目录重命名 = 用户可见的破坏性变更**。

### 2.3 跨宿主目录约定

- **`.agents/skills/` 已是事实标准**：Codex CLI 官方按此路径扫描；Cursor 读 `.claude/skills/` + `.claude/agents/`；多家把 `.agents/` 当唯一可信源。
- CloudBase 的规则值得抄：**`config/source/` 是手工真源 → 自动同步出镜像 → 生成产物禁止手改**。
- sickn33 的声明同样值得抄：**「GitHub 仓库是权威源，托管目录与浏览器 Workbench 仅为辅助发现/审查界面」**。

### 2.4 对本仓的直接发现

- ⚠️ **源目录与镜像目录混居**：`skills/`（真源）与 `.codebuddy/skills/ .claude/skills/ .agents/skills/ .codex/skills/`（4 份镜像副本）同时存在 → **真源漂移风险**。
- 本仓 `install_skills.py` 只做「复制到 N 个目标」，**缺「校验」与「名称冲突检查」两段**。

---

## 3. Python 工具的 agent 暴露机制（子代理 C）

### 3.1 分工原则（子代理给的判定表要点）

| 维度 | CLI 子命令 | MCP tool | 只写成 Skill |
|---|---|---|---|
| 本质 | 确定性本地操作 | 需要工具发现/长连接/认证的外部系统 | 流程编排、决策规则、确认话术 |
| token 成本 | ~0 | 懒加载后约 8.7k；**名字仍常驻** | 启动只加载 name/description |
| 可复现/审计 | 强 | 中 | 弱 |
| 人工确认 | `--dry-run` 默认 + `--yes` 显式 | elicitation 表单 | 写流程规范 |

**添加顺序的社区共识**：`AGENTS.md/CLI → MCP（需要认证时）→ Skill（同一流程反复出现时）`。

**对本项目的判断**：本地数据 + 人工确认 → **主战场是 CLI + Skill**；MCP 的收益低（无 OAuth、无远端），价值只在于「让不认技能的宿主也能用」。

### 3.2 真实样本（可借鉴的机制）

- **`oraios/serena`（29.1k★）**：CLI 是壳、MCP 是核。`[project.scripts] serena = "serena.cli:top_level"`；MCP 是其中一个子命令 `serena start-mcp-server --transport stdio`。三条可直接抄：
  1. **`--project-from-cwd`**：自动探测项目根（最近的 `.serena/project.yml` 或 `.git`）→ **正好治本仓「只能在本仓库根跑」的病**；
  2. **stdout 绝不能写日志**（MCP 用 stdout 通信，日志走 stderr/文件）；
  3. 会改文件的操作支持 **`--dry-run` 预览**；只读命令**始终退出码 0**。
- **`mcp-server-git`（官方）**：`[project.scripts] mcp-server-git = "mcp_server_git:main"`，同时支持 `uvx` / `python -m` / Docker；工具名 `git_status`、`git_commit`…（**动词_名词 + 服务前缀**）；读类与写类**同一个 server**，靠**注解**区分风险。
- 返回体控制：设字符上限（约 25k）并返回 `truncated / has_more / next_cursor`。

### 3.3 写入确认与安全（子代理结论）

- **写入确认必须有协议/服务端硬闸门**，不能靠系统提示词：`--dry-run` 默认 + `--yes` 显式；MCP 用 elicitation + destructive 预览。
- 安全底线：路径 `realpath` 解析后做**白名单前缀校验**（防 CWE-22 与 symlink 逃逸）、默认拒绝、**只读模式下根本不注册写工具**、审计日志。

---

## 4. 坑与反面证据（子代理 D）

### 4.1 最该避免的三件事

1. **不要让技能名重名**。技能身份 = 目录名 = frontmatter `name`，**同名静默覆盖**（不报错）。本仓的 `apply / jd / resume / track / recruit-coach` 都是高概率通用名，`resume`/`apply`/`track` 尤其容易撞。→ 上架前加作用域前缀。
   - 真实案例：`microsoft/apm #2629`（两个同名 skill 条目**静默合并、后者胜出、无任何警告**，被以供应链安全视角提出）；`QwenLM/qwen-code #4437`（自动技能**静默覆盖用户手写技能且不可恢复**，去重发生在写入之后，来晚了）。
2. **不要把「多宿主支持」写进路线图**。dsh 官方保留随时破坏兼容；各宿主格式/8KB 限制/TOML vs Markdown/权限块差异 → 单人 N 倍成本。正确姿势：**1 主宿主 + 1 次宿主，或只做纯本地技能**。
3. **不要以为上架市场 = 免费曝光**。插件会被**复制到 `~/.claude/plugins/cache`**，无法用 `../` 引用目录外文件；**设了 `version` 就要每次发版手动 bump，否则用户永远收不到更新**。对隐私敏感项目，最稳的是**本地技能 + 用户自行 clone/软链**。

### 4.2 Claude Code 市场硬约束

- **16 个保留名**第三方不可用（`claude-code-marketplace`、`claude-code-plugins`、`claude-plugins-official`、`claude-plugins-community`、`claude-community`、`anthropic-marketplace`、`anthropic-plugins`、`agent-skills`、`anthropic-agent-skills`、`knowledge-work-plugins`、`life-sciences`、`claude-for-legal`、`claude-for-financial-services`、`financial-services-plugins`、`first-party-plugins`、`healthcare`）；**冒充官方名同样被阻止**。

---

## 5. 未确认清单（子代理输出被截断，待补）

- dsh：`cordis.patch.yml` 的完整字段语义；`defineTool` 的 `output.presentationMeta` 全量约定；npm 发布所需的 `files`/`prepare` 细节。
- Claude Code：marketplace.json 的**全量字段**（子代理提到 `strict`、`source`，但完整校验规则未确认）与 `/plugin validate` 的实际报错集合。
- CloudBase 的 `build-compat-config.mjs` / `sync-claude-skills-mirror.mjs` 源码细节（只拿到行为描述）。
- wshobson 的 `capabilities.py` 能力矩阵结构。
- 8KB skill 上限的出处与适用范围（子代理在坑的报告里提到，未给出官方链接）。
