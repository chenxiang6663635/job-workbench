# 通用秋招工作台设计方案（v2.0）

日期：2026-08-30
状态：执行中
前置文档：`2026-08-30-autumn-recruit-workbench-design.md`（v1.0，个人工具定位，已被本文档取代）

---

## 1. 定位变更

v1.0 建的是"某位使用者的秋招工作台"。使用者明确更正：项目目标是**开发一个通用的工作台**，不是只给单个使用者用。本项目作为使用者的自用工具，同时要能被泛化复用。

三个决策（用户已定）：

| 维度 | 决策 |
|---|---|
| 领域范围 | 先同领域，架构预留跨领域。本期交付暖通版（词典内置），领域配置做成可插拔插件 |
| 运行时 | 兼容主流 AI CLI（AGENTS.md + skills 目录），放弃 CodeBuddy 专属能力 |
| 数据处置 | 分层但同仓：`template/`（通用骨架+示例）与 `personal/`（真实数据） |

## 2. 盘点：改的是什么

| 类别 | 命中 | 说明 |
|---|---:|---|
| 个人身份硬编码 | 44 文件 | 真实姓名、某节能率、某 SCI 期刊、某商业改造项目（脱敏表述，原值属个人隐私） |
| 领域术语 | 88+ 文件 | `04_知识库/` 30 份全暖通专属，单文件最高 239 处 |
| 脚本层硬编码 | 2 文件 | 仅 `resume_build.py`（2 个简历文件名）与 `tracker.py`（1 处注释） |

**关键结论**：被绑死的是**配置层与内容层**，不是脚本层。评分校验、CSV 读写、看板生成本来就与领域无关。

## 3. 架构：三层分离

```
工具层   tools/ + skills/        领域无关，任何人可用
领域层   template/profiles/      可插拔插件，本期内置 hvac-cooling
用户层   personal/               某个人的资产，从 template 初始化
```

单向依赖：用户层 → 领域层 → 工具层。工具层不认识领域层，领域层不认识用户层。

## 4. 目录结构

```
autumn-recruit-workbench/
├── README.md                    通用工作台主文档（上手指南）
├── AGENTS.md                    跨运行时 AI 约定入口
├── .gitignore
├── template/                    【通用骨架】
│   ├── AGENTS.example.md        候选人档案模板（待填写）
│   ├── README.md                模板使用说明
│   ├── profiles/                【领域插件】
│   │   └── hvac-cooling/        暖通制冷与数据中心冷却（本期内置）
│   │       ├── profile.md       插件元信息
│   │       ├── lexicon.md       三级词典 Primary/Secondary/Weak
│   │       └── directions/
│   │           ├── datacenter.md
│   │           └── hvac.md
│   └── workspace/               【空骨架 + 填写说明】
│       ├── 00_事实库/
│       ├── 01_岗位池/
│       ├── 02_简历工坊/
│       ├── 03_面试准备/
│       ├── 04_知识库/
│       └── 05_投递追踪/
├── skills/                      【跨运行时技能】单一源
│   ├── jwb-recruit-coach/       评分标准 + 通用红线
│   ├── jwb-jd/
│   ├── jwb-apply/
│   ├── jwb-track/
│   └── jwb-resume/
├── tools/                       【通用脚本】Python 3.8，零第三方依赖
│   ├── init_workspace.py        从 template 初始化 personal/
│   ├── install_skills.py        skills 分发到各家 CLI 目录
│   ├── jd_score.py
│   ├── tracker.py
│   ├── resume_build.py
│   └── report.py
├── personal/                    【个人实例】用户的真实数据
│   ├── AGENTS.md                个人档案（硬门槛事实、红线）
│   ├── config/                  软链或副本指向 template/profiles/<选中的插件>
│   └── 00_事实库/ ... 05_投递追踪/
└── docs/specs/
```

### 关于 `personal/` 是否 gitignore

**决定：纳入版本管理，不 gitignore。**

理由：用户明确要求「用 git 管理」，且当前只有本地仓库无远程，泄露风险为零。若 gitignore，用户每次新增文件都需 `git add -f`，反而容易漏提交。

代价：分享仓库前需移除 `personal/`。README 与 `.gitignore` 中均写明此警告。

## 5. 领域插件契约

一个插件 = 1 个共用词典 + N 个方向。新增领域只需新增一个目录，不改任何代码。

```
template/profiles/<domain-id>/
├── profile.md        # id、名称、适用人群、维护记录
├── lexicon.md        # 三级词典：Primary / Secondary / Weak
└── directions/
    └── <direction-id>.md   # 方向锚点表 + 该方向特有词
```

解析时通过 `--domain <id> --direction <id>` 定位。方向不属于当前领域时回退该领域的第一个方向，并在解析卡标注「结论仅供参考」（沿用 v1.0 裁决 B）。

本期内置 `hvac-cooling`，含 `datacenter` 与 `hvac` 两个方向——即 v1.0 的两个 config 文件，拆分重组。

## 6. 脚本参数化

v1.0 脚本硬编码了仓库内的固定路径。v2.0 改为：

- 所有脚本接受 `--workspace` 参数，默认 `personal/`
- 领域配置查找顺序：workspace 的 `config/` → `template/profiles/<domain>/`
- `resume_build.py` 改为**扫描 `02_简历工坊/pdf/` 下的 `resume_*.html`**，不再硬编码文件名
- `jd_score.py` 与 `report.py` 本就无硬编码，只需接 `--workspace`

脚本数量维持 **6 个**：`fix_links.py` 是个人重组的一次性工具，移入 `docs/deprecated/`；新增 `init_workspace.py` 与 `install_skills.py`，净增 1 个，但这两个是通用工具的必要组成（新人上手第一步 + 跨运行时分发）。当前 `tools/` 下共 6 个脚本：`init_workspace.py`、`install_skills.py`、`jd_score.py`、`resume_build.py`、`report.py`、`tracker.py`。

## 7. 跨运行时兼容

各家 CLI 的 skills 目录不同（`.claude/skills/`、`.codebuddy/skills/`、`~/.agents/skills/`）。方案：

- 仓库内保留 `skills/` 作为**单一源**
- `tools/install_skills.py` 检测本机已装的 CLI，把 skills 复制或软链到对应目录
- `AGENTS.md` 作为跨运行时约定入口，各家 CLI 都会读取

这样不依赖对任何一家具体约定的猜测，且用户新装一个 CLI 后重跑安装脚本即可。

## 8. 诚实红线：通用 vs 个人

v1.0 的七条红线中，**通用的只有两条**：

- 第 6 条：简历每个动词都要经得起 5–10 分钟追问，不把「参与」一律升级为「负责」
- 第 7 条：知识缺口用诚实的桥梁回答，永不编造经历

前五条（不认领某前端模块、某节能率的措辞、不包装某数据中心交付、项目一边界、项目二边界）**全部是个人专属事实**，放入 `personal/AGENTS.md`。

`template/AGENTS.example.md` 提供通用两条 + 「自定义红线」填写区，并给出填写示例（含个人版那五条作为示范，供用户参照改写自己的）。

## 9. 迁移映射

| v1.0 | v2.0 |
|---|---|
| `CODEBUDDY.md` | `template/AGENTS.example.md`（模板）+ `personal/AGENTS.md`（实例） |
| `config/direction_datacenter.md` | `template/profiles/hvac-cooling/directions/datacenter.md` |
| `config/direction_hvac.md` | `template/profiles/hvac-cooling/directions/hvac.md` |
| 两文件中共用的词典部分 | `template/profiles/hvac-cooling/lexicon.md` |
| `config/ats_required_facts.txt` | `personal/config/ats_required_facts.txt`（个人专属） |
| `00_事实库/` … `05_投递追踪/` | `personal/` 下同名 |
| `.codebuddy/skills/` | 仓库根 `skills/` |
| `.codebuddy/commands/` | 删除（跨运行时不需要，且未被官方文档确认） |
| `.codebuddy/rules/` | 内容并入 `AGENTS.md` |
| `tools/fix_links.py` | `docs/deprecated/`（个人重组一次性工具） |
| `99_归档/` | `personal/99_归档/` |
| `docs/specs/*v1.0*` | 保留，标注已被取代 |

## 10. 实施顺序

1. 建 `template/` 骨架与 `skills/`
2. `git mv` 现有模块 → `personal/`
3. 领域插件化（拆分 config）
4. 档案模板化
5. 脚本参数化
6. 安装脚本 + README/AGENTS.md
7. **端到端验证**：用 `template/` 的示例数据跑通，而非个人数据——这是通用工具，验证必须用示例

## 11. 与 v1.0 的关系

v1.0 的评分框架（四维度、Eligibility Gate、阈值档位）、追踪表设计（15 字段、批次维度、九级阶段）、PDF 流水线（ATS 三项校验）全部保留，这些设计本身是通用的。变的只是**它们读什么配置、操作哪个目录**。
