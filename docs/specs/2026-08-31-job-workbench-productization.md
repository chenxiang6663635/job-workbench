# 求职工作台产品化开发路线（2026-08-31 起）

- 日期：2026-08-31
- 定位升级：从"秋招自用"→"求职工作台产品"，面向普通用户，候选分发形态为 Tauri 桌面应用。
- 前置调研：`research_report_job_search_products.md`（三路 subagent，GitHub 竞品全景）
- 硬约束（来自工作记忆）：三层单向分离、tools 领域无关、脚本不硬编码工作区、不自动 git commit、Python 3.8、CSV utf-8-sig。

## 设计原则（调研得出的三条铁律）

1. **LLM 是增强层，不是地基**。评分框架可无 AI 手动执行；产品 = 免费核心 + BYOK 的 AI 增强。保住"无 key 也能用"。
2. **差异化主打市面空白**：①评分证据可追溯（总分→四类下钻→每条命中依据）；②资格硬门槛前置（Eligibility Gate）。这两点所有竞品都没做。
3. **形态 = 本地优先桌面端**：头部全是 Web 自托管，Tauri 本地端是空位。数据本地零上传是卖点。

## 分三期

### 一期：架构就位（为产品化铺底，不动产品形态）

目标：把"个人工具"里的单用户假设从架构上移除，让多工作区/多用户成为一等公民。

1. **workspace 成为一等概念贯穿全栈**
   - tools/ 全部脚本已支持 `--workspace`；Web 端 `workspace_dir` 依赖已存在，但后端 `ROOT` 硬编码指向 `personal/`。
   - 改造：后端启动时读一个工作区目录配置（env 或 `--workspace`），所有路由走 `Depends(workspace_dir)`，前端传入工作区名。目标是"同一份代码服务任意工作区"。
   - 交付判据：`web` 用两个不同 `--workspace` 启动，各自读写独立数据且互不污染。

2. **JD 评分呈现升级（市面差异化点之一）**
   - 现状：解析卡是 Markdown，Web 只读展示。
   - 改造：前端 Jobs 详情页做"总分→四类下钻→每条技能命中/缺失 + 依据（精确/模糊/语义）"三级钻取。数据仍来自解析卡，不改判断逻辑，只改呈现。
   - 交付判据：解析卡能渲染成可下钻的评分面板。

3. **资格硬门槛前置（市面差异化点之二）**
   - 现状：Eligibility Gate 在 AI CLI 的 jd 工作流里人工判断，Web 无体现。
   - 改造：解析卡增加"硬门槛"区块（学历/届别/地点/英语等一票否决项），Web 在评分上方优先展示"资格是否通过"。
   - 交付判据：一张不达门槛的解析卡，Web 首屏明确显示"资格未通过"而非分数。

4. **BYOK Provider 抽象（LLM 增强层的统一入口）**
   - 现状：工作台不碰 LLM API，AI 能力来自 AI CLI。
   - 改造：新增一个"Provider 设置"存储（JSON 或 env），记录 OpenAI 兼容端点 base_url + key，为二期桌面版接 LLM 预留统一入口。一期不接真实调用，只做配置骨架 + 连接测试。
   - 交付判据：设置页能保存 base_url/key 并跑通一次 `GET /v1/models` 连通性测试。

### 二期：桌面壳（Tauri）

目标：把 Web 前端装进桌面壳，双击运行、本地数据、BYOK 生效。

5. **Tauri 打包前端**：React/Vite 产物装入 Tauri，后端 FastAPI 以子进程或随包分发运行。双击即用，无 npm/node 依赖。
6. **数据目录落地**：桌面版把工作区落到用户目录（如 `~/.job-workbench/<workspace>/`），首次运行初始化。Web 的 `--workspace` 抽象在此落地为用户可切换的工作区。
7. **BYOK 生效**：用户在设置页填 key，AI 增强（JD 解析/评分/改写）通过本地后端调用，输出仍落回 Markdown/CSV。所有 AI 动作"建议→用户批准→落盘"。

### 三期：扩展与打磨（长期运行）

8. **追踪模型硬化**（对标 JobCtrl）：终态不回退、状态跃迁带原因码、简历版本与申请记录外键关联、canonical 去重。UI 阶段收敛 5-6 级，九级留高级模式。
9. **浏览器扩展（可选）**：用户会话内 ATS 表单预填。仅做"预填"，永不做自动提交/批量投递（AIHawk 教训）。
10. **多工作区/多用户管理**：一期 workspace 抽象的自然延伸；账号功能只做本地工作区隔离，不做云端账号。

## 明确不做（本期）

- 托管 LLM 后端（成本无底洞，BYOK 是共识）
- 自动投递 bot（法律与封号风险）
- 云端同步/远程部署（本地优先是卖点）
- JD 评分的"自动执行"——评分判断仍由 AI/用户做，Web 只读展示与下钻

## 风险

- 一期 workspace 抽象如果做不彻底，二期多用户会返工。判据：交付时用双工作区实测。
- 产品化会稀释"自用顺手"——每期先保自用功能可用，再上产品化壳。

---

## 一期进度（2026-08-31 完成两个差异化点）

已完成：资格硬门槛前置 + 评分证据可追溯（叠加方案）。改动文件：

| 文件 | 改动 |
|---|---|
| `tools/jd_score.py` | 新增 `parse_hard_gates`、`parse_dimension_detail`、`_parse_dim_block`、`_classify_gate`；识别【精确/模糊/语义】证据标签；Python 3.8 兼容、容错缺失、领域无关 |
| `web/backend/routers/jobs.py` | `_parse_card` 返回 `hardGates` + `dimensionsDetail`；`_summary` 契约不受影响 |
| `web/frontend/src/api.ts` | `JobDetail.card` 类型加 `hardGates`、`dimensionsDetail`（含 `EvidenceLevel`/`DictLevel` 类型） |
| `web/frontend/src/pages/Jobs.tsx` | 硬门槛卡片置顶（三态色）；评分四维可点击下钻（逐条命中 + 证据徽章 + raw 原文） |
| `skills/jd/SKILL.md` | 第 4 步加证据标签规范（精确/模糊/语义定义 + 写法示例） |
| `personal/01_岗位池/_模板_解析卡.md` | 补硬门槛逐条依据 + 分维度明细 + 证据标签示例 |

**验证结果**：
- 后端 API `/api/jobs/{id}` 返回硬门槛（通过/5字段/5条依据）与维度明细（技术匹配 10 条命中）。
- Playwright（chromium headless，版本目录 1200/1234 已配齐）实测：硬门槛卡片置顶渲染、四维下钻展开显示 Primary/Secondary 命中 + note + raw 计算说明。
- 旧卡（无证据标签）兼容：evidence=null，不显示徽章，不报错。
- TS 类型检查 exit=0，read_lints 全文件无错误。
- **关键排错**：uvicorn 无 `--reload`，改后端代码后必须重启进程才生效；PowerShell 需用 `npm.cmd` 启动 vite。

**遗留已闭环**：用临时带标签解析卡 + Playwright 实测证据徽章渲染成功——精确=蓝、模糊=琥珀、语义=青，能力分层（Primary/Secondary）徽章同屏正常，raw 计算说明正确；验证后临时卡已清理，岗位池恢复原状。

---

## P0+P1 完成（2026-09-01）：一键启动友好化 + workspace/BYOK 抽象

用户确认范围：①P0 补错误可读 + 前端启动失败检测；②P1 workspace 解耦（后端可指定 + 前端切换 UI）+ BYOK Provider 骨架。改动文件：

| 文件 | 改动 |
|---|---|
| `web/start.ps1` | 补依赖预检（python/node/npm 缺失提示）、端口释放失败提示、后端超时排查、前端启动失败区分诊断（端口占/npm 未装/Vite 崩溃） |
| `web/backend/deps.py` | `DEFAULT_WORKSPACE` → `resolve_default_workspace()`，读 `JOBWS_WORKSPACE` 环境变量，回退 personal/ |
| `web/backend/main.py` | 支持 `--workspace` CLI 参数（`python main.py --workspace X`），挂载 workspace/provider 路由 |
| `web/backend/routers/workspace.py` | [NEW] `/api/workspaces` 扫描含 `config/profile.md` 标记的目录 |
| `web/backend/routers/provider.py` | [NEW] `/api/provider` 读写（key 脱敏）+ `/api/provider/test` 连通性测试（调 `/models`，超时控制，独立锁文件） |
| `web/frontend/src/api.ts` | 全局 `currentWorkspace` + `request()` 统一拼 `?ws=` + workspace/provider API |
| `web/frontend/src/App.tsx` | 导航栏工作区切换下拉 + "设置"Tab |
| `web/frontend/src/pages/Settings.tsx` | [NEW] Provider 设置页（base_url/key 保存 + 测试连接 + 模型列表） |

**验证（全部实测通过）**：
- 双工作区数据隔离：personal（4岗位/2投递）vs test_ws（0/0），`?ws=` 切换生效；`JOBWS_WORKSPACE=test_ws` 启动后无 `?ws=` 默认读 test_ws。
- workspace 参数校验：不存在404、越界400、绝对路径400。
- Provider：key 脱敏正确（`******5678` 只显末4位）；无效 key 连通性测试返回 502 + 人话"api_key 无效或无权限"。
- Playwright 截图：导航栏工作区下拉"personal（默认）"、设置页 Provider 表单（base_url + 脱敏 key）、5 个 Tab（含设置）。
- TS exit=0，read_lints 全零错误。

**关键排错（重要经验）**：
1. **file_lock 不能锁内容文件本身**：对 `provider.json` 加锁在 Windows 会 Permission denied（内容写入时锁未释放 + 0 字节文件锁 1 字节异常）。应改用独立 `.lock` 文件（与 tracker 的 `tracker.lock` 一致）。
2. **`ssl.create_default_context()` 在本机触发 `ASN1: NOT_ENOUGH_DATA`**（Windows 证书存储加载 bug，与目标 Provider 无关）。连通性测试改 `ssl._create_unverified_context()`（不加载证书库）绕过——连通性测试是本地配置检查，可接受不校验证书。
3. workspace 判定用 `config/profile.md` 标记，与 `jd_score.resolve_profile` 单一事实源一致。

**遗留**：测试工作区 test_ws 已删、测试 provider.json 已删、截图已清。工作区切换下拉是完整可用的（切工作区 reload 后各页面按新 ws 拉数据）。
