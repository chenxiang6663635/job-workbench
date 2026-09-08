# 贡献与开发流程

本文定义本仓库的开发流程约束。适用对象：维护者本人（第一用户）、AI 协作者与外部贡献者。
数据分层与领域约定见 [AGENTS.md](AGENTS.md)；文档索引见 [docs/README.md](docs/README.md)。

## 项目定位（先读这个）

- **自用优先**：维护者是第一用户。把项目当最严格的真实用户去用，但**不把自己当市场**——dogfooding 能回答"它坏了吗 / 难用吗"，不能回答"有人想要吗"。
- **单人维护**：流程以"最小可行"为纲。凡是维护成本超过收益的工程化设施，一律不做（见文末"明确不做"）。
- **仅本地 git**：曾长期无远程与 CI；开源后以 GitHub Actions 跑测试与构建作为质量门，分发仍以手动归档安装包为主。

## 隐私约定（开源后生效，贡献前必读）

- **本仓库不含真实个人数据**：`personal/` 已整体加入 `.gitignore`，历史中的真实数据也已清洗。
- **禁止提交任何 `personal/` 内容**：包括其中的文件路径、真实公司名、简历片段、投递记录、截图。
- **禁止提交真实身份信息**：姓名、电话、邮箱、学校、证件号、照片——文档与示例中一律使用占位（`示例公司A`、`sample@example.com`、`你的姓名`）。
- **示例用假数据**：测试与模板沿用既有假数据（`13800000000`、`z@x.com`、`示例公司A`），不要替换成真实信息。
- **发现泄露怎么办**：直接提 issue 说明位置（**不要贴出泄露内容本身**），维护者会用 `git filter-repo` 清洗历史。

## 新需求四道门（每次动手前依次过）

任何新需求——不管来自自己的使用痛点还是他人建议——先过这四道门：

1. **这是第几次？**（rule of three）
   第一次 → 写一次性脚本或文档，**不进代码库**；第二次 → 把硬编码抽成配置项；第三次 → 才抽象成通用功能。
2. **含不含个人事实？**
   任何只属于"某个人"的信息（个人事实文件的内容、个人词表、个人清单）→ 一律进 `personal/` 配置层或领域插件，**永不进核心代码**。这条能过滤掉大部分自用需求。
3. **泛化代价多少？**
   ≤ 1 小时 → 顺手做；> 1 小时 → 只开 issue 记录，不为"顺手"破坏结构。
4. **动不动数据模型或诚实红线？**
   涉及数据格式变更、或触碰 [AGENTS.md](AGENTS.md) 的诚实红线 → 必须另开 issue/设计说明论证，**禁止因一次使用场景的紧迫性直接改**。

**结构性保险**：每周固定留 1 条"产品化任务"（配置化 / 文档 / 测试），与自用任务分开推进。没有这条，自用优先会让产品化无限延后。

## 分支策略（分级 PR + trunk-based）

- `main` 是唯一主干。按**改动是否影响运行时行为**分级，不搞一刀切：

**必须走 PR**（影响运行时行为的改动）：

- `tools/`、`web/backend/`、`web/frontend/` 的代码修改，`tests/` 用例
- 依赖变更（`requirements*.txt` / `package.json`）；CI / workflows 配置
- 数据模型 / schema 变更；触碰 [AGENTS.md](AGENTS.md) 诚实红线的内容
- PR 门槛：CI 绿（pytest 33 项 + 前端 build 两 check 全过——**PR 合并前的流程硬要求，红不许合**）+ 对照 [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) 自查 + 以 reviewer 视角通读 diff（重点看隐私与四道门）；Squash and merge，合后删分支

**可直推 main**（不影响运行时的纯文本与资料类）：

- 文档（README / `docs/` / CHANGELOG / CONTRIBUTING / 注释）、截图与 demo 产物、typo 与链接修复
- 前提：不破坏构建与数据安全；**拿不准 → 一律按 PR 处理**（宁走 PR，不冒险）

- 分支命名（PR 路径）：`feat/<issue号>-<slug>`、`fix/<issue号>-<slug>`、`docs/<slug>`；存活 ≤ 1–2 天，合完即删。
- 兜底（出错了怎么办）：数据快照备份 + `git revert`——squash 提交可整体回滚，不污染主干历史。
- 只在三种情况考虑分支而非直推：可能放弃的实验 / 半天以上完不成的重构 / 会临时破坏"当前可用状态"的改动。
- **不设** `develop` / `release` / `hotfix` 分支。

## 提交规范（Conventional Commits）

格式：`<type>(<scope>): <描述>`

- `feat`：新功能 → 版本号 minor 位 +1
- `fix`：修 bug → patch 位 +1
- `docs` / `chore` / `refactor` / `data` / `job`：不触发版本号
- 破坏性变更：`!` 后缀或正文 `BREAKING CHANGE:` 段
- **数据操作与代码分开提交**：往工作区录入数据的提交用 `data:` / `job:` 前缀，不与功能提交混合

## 版本规则（0.x 简化 semver）

- 版本号唯一来源：`web/electron/package.json` 的 `version` 字段。
- `feat` → `0.x.0`；`fix` → `0.x.y+1`；破坏性变更 → 新增 `0.x` 段并写入 CHANGELOG。
- 升 `1.0.0` 的时机：**自用稳定 + 承诺本地数据向后兼容**。不要用 major 号表达"功能变多"。
- 当前版本：**0.1.0（2026-09-08 已打 tag `v0.1.0`）**。后续按规则 bump 并打新 tag。

## 发布流程（手动归档）

从 `main` 打 tag，不从分支发：

1. **冒烟验证**（CI 已跑 33 项自动化测试，人工冒烟不可省）：跑构建脚本产出安装产物 → **安装运行一次** → 用旧数据打开七个页面各操作一遍。
2. bump 版本号（`web/electron/package.json`）。
3. 把 [CHANGELOG.md](CHANGELOG.md) 的 `Unreleased` 段改为版本号 + ISO 日期。
4. `git tag -a v0.1.0 -m "..."` 并提交。
5. 构建产物按版本归档到仓库外目录（产物已被 .gitignore 排除）。

**hotfix**：fix-forward——开 `fix/` 分支走 PR 合入 `main`，再打新 patch tag。**不**从旧 tag 拉 hotfix 分支。
**撤回坏版本**：递增到更高版本号重发；重发同名版本无效。

**自动更新不做**：仓库已公开（2026-09-08 推送），剩余阻碍是代码签名（macOS 必需）；分发仍走手动安装包。`personal/` 隐私剥离已完成（整体 gitignore + `git filter-repo` 历史清洗）。

## 可持续性约定

- **时间盒公开化**：在 README 写明每周投入时长与"可能几天不回复"。
- **停工窗口**：面试周 / 笔试周不开发——项目为求职服务，不是求职的对立面。
- **issue 上限**：未处理 issue 超 30 个即 triage 关闭，防积压瘫痪。
- **愿景先行**：重大方向先写设计说明（`docs/specs/`），人可以离开，愿景让项目继续走。

## 对 AI 协作者

- 本文件与 [AGENTS.md](AGENTS.md) 是互补关系：这里管"流程"，AGENTS.md 管"数据分层与诚实红线"，互不重复。
- AI 修改代码时同样受四道门约束；发现走不到第三道门的需求，应建议降级为一次性脚本或 `personal/` 配置。
- 提交前跑通验证（脚本 / lint / tsc），不把"应该能跑"写进提交信息。
- **本地验证链（与 CI 同款）**：`pip install -r web/backend/requirements-dev.txt` → `python -m pytest tests/ -q`（33 项基线）→ 前端 `npm run build`（Windows 用 `npm.cmd`）。

## 开发辅助工具（MCP / 代码图谱，开发者与 AI 用，非产品）

项目区分**产品运行时依赖**（终端用户跑起来需要：浏览器 + Chrome + `tools/` 脚本 + Web 层）
与**开发辅助**（开发者在写代码时借力的工具：GitNexus 影响面分析、CodeGraph 代码图、
Playwright 点页面验证）。前者在仓库里、随项目交付；后者是**开发者个人环境**的工具，
不进产品链路。因此"CONTRIBUTING 提到 GitNexus/Playwright"与"产品不含它们"不矛盾。

若要在本仓库开发时用上代码图谱工具，索引是**按仓库生成**的运行时产物，已被 `.gitignore`
排除（`.gitnexus/`、`.codegraph/`），clone / 换机后跑一次重建：

```
powershell -ExecutionPolicy Bypass -File scripts/index_dev_tools.ps1
```

前提是全局装好 `gitnexus` 与 `@colbymchenry/codegraph`（`npm i -g ...`）。MCP 声明样板见
`.codebuddy/mcp.example.json`——复制到用户级 `~/.codebuddy/mcp.json` 并替换其中的路径占位符。

**隐私提醒**：`personal/` 已随开源清洗出仓库，但本机工作区 `personal/` 仍是真实数据（简历、联系方式）。代码图谱索引会把部分文件名/符号
记进 `.gitnexus/`/`.codegraph/`（本机缓存）。这两个目录已 gitignore 不会进仓库，但**别把它们
本体外发**；索引进展用 `gitnexus list`、`codegraph status` 查看。

注意：产品侧 `CONTRIBUTING` 明确不做 Playwright **E2E 测试**（见下节），那是"把 UI 自动化
写进 CI/测试套件"的取舍；开发时**用 Playwright 手动点一次页面做验证**不属此列，不受限。

## 明确不做（过度工程）

`develop`/`release`/`hotfix` 分支、semantic-release、GitHub Projects 看板、需求投票工具、复杂 label 体系、独立 roadmap 站点、Playwright E2E、代码签名。
（依据：`docs/research/report_dev_workflow.md` —— 单人维护项目的最小可行取舍。例外：最小 CI（2026-09-08 上线，pytest + 前端构建）；**分支保护（2026-09-08 起启用）**——线性历史 + 禁 force push（含 admin）。GitHub 分支保护无法按路径区分"代码 vs 文档"（required checks 会连带禁止一切直推），故分级靠"分支策略"节的规则自律执行，出错靠 revert 兜底。）
