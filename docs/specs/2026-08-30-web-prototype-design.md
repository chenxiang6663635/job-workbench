# Web 界面层设计（本地原型）

日期：2026-08-30
状态：最小闭环已交付并验证
前置文档：`2026-08-30-general-workbench-design.md`（v2.0，通用工作台架构）

---

## 1. 定位与边界

在 CLI 工作台之上增加浏览器界面，**与 CLI 共享同一份 Markdown + CSV 数据源**。

Web 不是另一套数据，而是同一份文件的另一个视图。这一条是整个设计的基石：

- 在网页里新增的投递记录，CLI 命令同样能查到
- 用 CLI 或 AI 生成的解析卡，网页详情页自动展示
- 所有改动都能被 `git diff` 追踪

由此推出一条硬约束：**Web 层不得引入缓存**。缓存会让 Web 与 CLI 看到不同的数据，直接违背"同一数据源"的前提，且这类不一致极难排查。

### 本期做

看板、追踪表、岗位池三个页面，能读写真实文件并持久化。

### 本期不做

| 边界 | 原因 |
|---|---|
| 打包与分发 | 用户明确"先原型验证价值，确认好用再决定形态" |
| 登录、多用户、用户隔离 | 属于分发形态决策之后的事 |
| JD 解析评分网页化 | 本地 AI CLI 运行在 IDE 里，无法从网页触发；接 LLM API 需 key，留待后续 |
| 简历 PDF 页面 | CLI 已解决，留作后续批次 |
| 改数据层格式 | Markdown + CSV 刻意保留：git 可 diff、AI 可直接读、Excel 可打开、不锁定用户 |

---

## 2. 架构

```
浏览器 (React:5173)
    │  JSON /api（Vite proxy 转发）
    ▼
FastAPI (8765)
    │
    ├─ deps.safe_join      路径穿越防护
    ├─ filelock           并发写保护
    │
    ▼
import tools/  ← 复用现有脚本，业务逻辑不重写
    │
    ▼
personal/  Markdown + CSV
    ▲
    ├── AI CLI（CodeBuddy，写解析卡）
    └── CLI 脚本（tracker.py 等）
```

**核心策略是复用而非重写。** `tools/` 下六个脚本共 33 个函数，后端通过 `sys.path.insert` 接入后直接 import，只有 HTTP 编排是新的。

### 复用的函数

| 来源 | 函数 | 用途 |
|---|---|---|
| `tracker.py` | `read_rows` / `write_rows` / `next_id` | 追踪表读写与 ID 生成 |
| `tracker.py` | `check_date` / `check_direction` | 字段校验 |
| `tracker.py` | `sort_key` | 排序（终态沉底 + 日期升序） |
| `report.py` | `count_by` / `parse_date` | 统计与日期解析 |
| `jd_score.py` | `parse_score_section` / `parse_dimension` / `verdict` | 解析卡评分读取与档位判定 |

---

## 3. 后端设计

### 3.1 模块职责

| 文件 | 职责 |
|---|---|
| `main.py` | FastAPI 入口、CORS、路由挂载、`sys.path` 接入 `tools/` |
| `deps.py` | `workspace_dir()` 依赖注入、`safe_join()` 路径安全、目录常量 |
| `filelock.py` | 跨平台文件锁（Windows `msvcrt` / Unix `fcntl`） |
| `routers/dashboard.py` | 看板统计 |
| `routers/applications.py` | 追踪表增删改查 |
| `routers/jobs.py` | 岗位池列表、新建、详情 |

### 3.2 三个并发与安全问题

**一、全局变量并发不安全**

`tracker.py` 原本用模块级 `WORKSPACE`，靠 `set_workspace()` 切换。CLI 单进程顺序执行无碍，Web 并发请求会互相覆盖工作区路径导致数据错乱。

改造方式：给核心函数加可选 `workspace` 参数，缺省回退全局。

```python
def resolve_ws(workspace=None):
    return os.path.abspath(workspace) if workspace else WORKSPACE
```

CLI 调用不传参，行为一行不变；Web 显式传参。**已验证两种模式互不污染。**

**二、CSV 并发写丢数据**

`write_rows` 是全量重读重写。网页上快速点两下即并发，后写覆盖先写，静默丢数据。

所有写操作持锁：

```python
with file_lock(lock_path):
    rows = tracker.read_rows(ws)
    rows.append(row)
    tracker.write_rows(rows, ws)
```

**三、路径穿越**

所有文件操作先归一化再校验不越界。本地单用户虽无攻击面，但这是要分发的产品的原型，习惯须从一开始养成。

```python
def safe_join(workspace, *parts):
    for p in parts:
        if os.path.isabs(p) or ".." in p:
            raise HTTPException(400, "非法路径片段")
    full = os.path.normpath(os.path.join(workspace, *parts))
    if not full.startswith(workspace + os.sep):
        raise HTTPException(400, "路径越出工作区")
    return full
```

### 3.3 API 契约

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/dashboard` | 漏斗、方向/批次统计、近七天待办、过期提醒 |
| GET | `/api/applications` | 列表，支持 `?stage=&direction=&batch=` |
| POST | `/api/applications` | 新增投递 |
| PATCH | `/api/applications/{id}` | 更新（仅阶段、下次动作、日期、备注、评分、投递日期、截止日期） |
| GET | `/api/jobs` | 岗位列表 |
| POST | `/api/jobs` | 新建岗位（公司、岗位、JD 文本） |
| GET | `/api/jobs/{job_id}` | 详情（JD 原文 + 解析卡解析结果） |

`PATCH` 可更新字段与 CLI 的 `UPDATABLE` 保持一致——**公司与岗位不可改**，需改则新建记录并把旧的标为已放弃。

服务启动后另有自动生成的交互式文档：`http://localhost:8765/docs`（FastAPI 自带 OpenAPI）。

### 3.4 dashboard 的实现边界

`count_by` 与 `parse_date` 是纯函数，直接复用。但 upcoming/overdue 的判定逻辑嵌在 `report.build_report` 内部、与 Markdown 拼装耦合，不便复用，本期在 backend 用十余行重写。

**后续改进项**：把该逻辑提取为返回结构化数据的函数，让 `build_report` 基于它生成 Markdown。这样 CLI 与 Web 共用同一判定，不会各写一份导致不一致。本期不做。

---

## 4. 前端设计

React + TypeScript + Vite + Tailwind + recharts。

### 4.1 文件结构

| 文件 | 职责 |
|---|---|
| `api.ts` | 类型定义与 API 客户端（统一 `request()` 封装） |
| `App.tsx` | 导航壳、后端连接状态指示、Tab 切换 |
| `pages/Dashboard.tsx` | 统计卡片、recharts 漏斗、方向/批次、待办、过期提醒 |
| `pages/Applications.tsx` | 筛选、表格、行内编辑、新增表单 |
| `pages/Jobs.tsx` | 卡片列表、建岗表单、详情分栏 |
| `index.css` | Tailwind 入口 + 深色主题全局样式 |

### 4.2 设计约束

**样式用 Tailwind**，深色主题（ink 色阶 + accent 青蓝），卡片 hover 上浮与光晕微动效，状态色区分（good/warn/bad）。

**空态必须优雅**。`personal/` 初始无数据，三个页面都要显示引导文案而非白屏。空态是真实的第一印象，不是边缘情况。

**输入用原生标签**。`input` / `select` / `button`，不用 div 模拟，保证可访问性与表单语义。

### 4.3 与后端的状态约定

后端未启动时，App 顶部状态灯变红并给出启动命令——避免用户面对空白表格不知所措。

---

## 5. 数据契约

### 5.1 追踪表 `personal/05_投递追踪/tracker.csv`

15 字段，UTF-8 **带 BOM**（`utf-8-sig`），Excel 直接打开中文不乱码。

`id, 公司, 岗位, 方向, 批次, 来源, 截止日期, 投递日期, 当前阶段, 下次动作, 下次动作日期, 简历版本, 评分, 归档目录, 备注`

阶段枚举：`待投 → 已投 → 笔试 → 一面 → 二面 → 三面 → HR面 → offer → 签约`，终态 `已挂` / `已放弃`。

方向 ID 取决于工作区装入的领域插件（`config/directions/*.md`），**不在前端或后端写死**。

### 5.2 岗位目录

```
01_岗位池/<公司>_<岗位>/
├── JD原文.md     完整原文，不改写不摘要
└── 解析卡.md     由 AI CLI 评分生成，网页只读
```

### 5.3 解析卡评分小节

`jd_score.py` 只解析 `## 评分`，其余供人阅读：

```
## 评分
技术匹配: 24/30
经历匹配: 18/25
方向契合: 26/30
培养与稳定性: 11/15
总分: 79
```

后端解析后返回结构化数据（四维度 + 总分 + 档位 + 加总是否自洽）。未评分或格式不完整时返回 `null`，前端显示"尚未生成解析卡"并说明如何生成——**不报错**。

---

## 6. 环境要求

| 项 | 版本 |
|---|---|
| Python | 3.8.19（已 EOL，需锁定依赖版本） |
| fastapi | <0.116（实测 0.115.14） |
| uvicorn | <0.31（实测 0.30.6） |
| pydantic | <2.10（实测 2.9.2） |
| Node | ≥18（实测 v24.15.0） |

**Python 3.8 是本项目的硬约束**，脚本禁用 3.9+ 语法。FastAPI 与 pydantic 新版本陆续放弃 3.8，故在 `requirements.txt` 中锁定上限版本。

**Windows 启动前端必须用 `npm.cmd`**，直接跑 `npm` 会静默失败（端口不监听但无报错）。这是一个坑，值得记住。

---

## 7. 已验证的行为

最小闭环从空态开始完整验证 12 步，全部通过：

1. 空态下三个 API 均返回 `total=0`，不崩溃
2. 空态页面显示引导文案，不白屏
3. 新增投递得 A001
4. 刷新后仍在（持久化生效）
5. 修改阶段与下次动作
6. 刷新后修改仍生效
7. 新建岗位并落盘 JD 原文
8. 岗位刷新后仍在
9. **CLI `tracker.py list` 读到网页新增的 A001**（双向互通成立）
10. `git status` 可见 `tracker.csv` 与岗位目录
11. CSV 前 3 字节为 `EF BB BF`（Excel 不乱码）
12. 清理后恢复空态，页面仍正常

### 验证方法

Playwright 浏览器内核未安装。改用已装的 Chrome 无头渲染抓取挂载后的 DOM：

```bash
chrome --headless --disable-gpu --virtual-time-budget=8000 \
       --dump-dom http://127.0.0.1:5173/ > page.html
```

再匹配关键文案。**这只验证 HTTP 200 不够**——必须确认 React 真的挂载并渲染了数据。

### 实施中发现并修复的两个缺陷

1. **jobs 路由拼路径漏了 `01_岗位池` 层级**，文件虽写入但 `hasJD` 恒为 `false`
2. **`tracker.sort_key` 当时是 `cmd_list` 的嵌套函数而非模块级**，Web 引用它必 500。已提升为模块级，CLI 与 Web 共用同一排序规则

---

## 8. 后续改进项

按优先级：

1. **提取 dashboard 统计逻辑**：把 upcoming/overdue 判定从 `report.build_report` 中抽出为返回结构化数据的函数，让 CLI 与 Web 共用（避免两处逻辑漂移）
2. **简历 PDF 页面**：后端已具备能力（`resume_build`），只差前端入口
3. **JD 评分网页化**：需先决定接入 LLM API 的隐私取舍
4. **分发形态**：确认好用后再决定桌面应用 / 自托管 / 云端。若走云端，数据层需重新评估（文件存储在多用户场景下不合适）
