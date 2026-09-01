# 求职工作台 · 使用手册

从零开始把工作台跑起来，以及日常使用的完整说明。

遇到问题先看最后的「常见问题」，覆盖了黑屏、端口占用等已踩过的坑。

---

## 一、一次性环境准备

只需做一次。已配好可跳过。

### 必装

| 软件 | 用途 | 检查命令 |
|---|---|---|
| Python 3.8+（conda 环境） | 后端与 CLI 脚本 | `python --version` |
| Node.js 18+ | 前端构建 | `node --version` |
| Chrome 或 Edge | PDF 生成（headless 渲染） | 一般自带 |

### 安装依赖（各一次）

```bash
# 后端依赖（fastapi/uvicorn/pydantic 已锁 3.8 兼容版本）
cd <仓库目录>\web\backend
pip install -r requirements.txt

# 前端依赖
cd <仓库目录>\web\frontend
npm install
```

### 初始化你的工作区（已有 personal/ 的跳过）

```bash
python tools/init_workspace.py --target personal --domain hvac-cooling
```

---

## 二、日常启动：Web 界面

### 方式一：一键启动（推荐）

```powershell
cd <仓库目录>\web
.\start.ps1
```

脚本会自动：清掉被占用的端口 → 启动后端（8765）→ 启动前端（5173）→ 等待就绪 → 自动打开浏览器。

**关闭方式**：关掉脚本所在的控制台窗口，两个服务一起停。

### 方式二：手动启动（需要看后端日志时用）

开两个终端：

```bash
# 终端一：后端
cd <仓库目录>\web\backend
python -m uvicorn main:app --port 8765

# 终端二：前端（Windows 必须用 npm.cmd，直接跑 npm 会静默失败）
cd <仓库目录>\web\frontend
npm.cmd run dev
```

### 访问地址

| 地址 | 是什么 |
|---|---|
| http://localhost:5173 | **工作台界面（日常用这个）** |
| http://localhost:8765/docs | 后端 API 交互文档（FastAPI 自动生成） |

> 前端把 `/api` 请求代理到 8765，所以浏览器只跟 5173 打交道。

---

## 三、Web 界面四个页面

### 看板（首页）

打开就是它。回答三个问题：投了几家、几家还在流程中、接下来七天该干什么。

- 顶部四张统计卡：投递总数 / 流程中 / 近七天待办 / 已过截止
- 投递漏斗：每个阶段多少人（待投→已投→笔试→…→签约）
- 近七天待办：下次动作日期或截止日期落在未来 7 天的记录
- 已过截止提醒：还停在「待投」但截止日期已过的记录（红色）

### 追踪表

所有投递记录的表格。三件事：

- **筛选**：顶部按阶段 / 方向 / 批次过滤
- **改状态**：点某行的「当前阶段」下拉框直接改（待投→已投→笔试…），改完自动保存
- **新增**：右上「新增投递」，填公司与岗位（必填）、方向、批次、评分等

> 方向下拉框的选项来自工作区装入的领域插件（`config/directions/`），不是写死的。

### 岗位池

管理你看过的岗位。每张卡片显示公司_岗位、评分、档位。

- **新建岗位**：粘贴完整 JD 原文（职责+任职要求），系统原样存档
- **点开详情**：左边 JD 原文，右边解析卡
- **解析卡**：评分由 AI 在 CodeBuddy 里完成后写入 `解析卡.md`，这里自动显示四维度进度条 + 总分 + 档位
- 还没评分的岗位显示"尚未生成解析卡"及操作指引——**网页不做评分**，评分是 AI 的工作

### 素材库

查看你自己的资产文件，两个分栏：

- **简历工坊**：简历 md 原文、生成的 PDF（内联预览）、照片
- **事实库**：5 张事实卡原文

只读——这些文件由 CLI/AI 生成维护，网页只负责看。

---

## 四、让 AI 干活：jd / apply 工作流

网页负责看和记，**判断类的工作交给 AI**。在 CodeBuddy 里用自然语言：

### 解析一个岗位（jd 工作流）

把 JD 原文贴给我，或者说"解析这份 JD"。AI 会：

1. 在 `personal/01_岗位池/<公司>_<岗位>/` 存 JD 原文
2. 跑硬门槛过滤（学历→专业→届数→英语→城市，对照 `personal/AGENTS.md`）
3. 通过后四维度评分（技术30/经历25/方向30/培养15），回查事实卡核验
4. 校验加总并输出档位（75+ 强烈投 / 60-74 投 / 45-59 斟酌 / <45 不投）

**硬门槛不过会直接拦下**，不打分不写材料。比如要求 CET-6 的岗位会被你的英语红线拦住。

### 生成投递包（apply 工作流）

说"给 XX 岗位生成投递包"。AI 会：选对应方向的简历版本 → 按需微调四处（项目事实不动）→ 生成 PDF → ATS 校验（页数/文本层/关键事实）→ 归档到 `05_投递追踪/applications/` → 写入追踪表 → 列出改动清单交你确认后 git 提交。

### 更新进展（track）

面试完说"把 XX 更新到一面"，或直接在网页追踪表里点下拉框。

### 改简历后重新出 PDF（resume 工作流）

说"重建简历 PDF"，或命令行：

```bash
python tools/resume_build.py --workspace personal --version hvac
```

---

## 五、CLI 命令速查（不用网页时）

所有命令在仓库根目录执行。`--workspace personal` 可省略（默认就是它）。

```bash
# 追踪表
python tools/tracker.py list                        # 全部记录
python tools/tracker.py list --due-within 7         # 未来 7 天到期
python tools/tracker.py list --stage 笔试           # 按阶段筛
python tools/tracker.py add --company "某公司" --role "岗位" --direction hvac --batch 正式批 ...
python tools/tracker.py update --id A001 --stage 一面 --next "准备口述" --next-date 2026-09-10

# 投递漏斗看板（Markdown）
python tools/report.py --stdout

# 简历 PDF + ATS 校验
python tools/resume_build.py --workspace personal            # 全部版本
python tools/resume_build.py --version hvac                  # 指定版本

# JD 解析卡评分校验
python tools/jd_score.py "personal/01_岗位池/<目录>/解析卡.md" --domain hvac-cooling --direction hvac
```

---

## 六、数据在哪、怎么备份

**所有数据都是纯文本文件**，在 `personal/` 下：

| 目录 | 内容 |
|---|---|
| `00_事实库/` | 项目/实习事实卡——唯一事实源 |
| `01_岗位池/` | 每个岗位一个目录：JD 原文 + 解析卡 |
| `02_简历工坊/` | 简历 md + HTML 模板 + 生成的 PDF + 照片 |
| `03_面试准备/` | 自我介绍、项目表达、题库、行为面、复盘 |
| `04_知识库/` | 30 份知识词典 |
| `05_投递追踪/` | tracker.csv + 每次投递归档 |
| `AGENTS.md` | 你的档案：硬门槛事实、诚实红线 |

**备份**：本地 git 已追踪全部文件，每次提交都是一个快照。想再稳一点：

```bash
# 在另一块磁盘/目录做镜像（不含工作目录改动）
git clone --mirror <仓库目录> d:\backup\autumn-recruit.git
```

> ⚠️ 分享仓库给任何人之前，先确认 `personal/` 的处置（含姓名、照片、联系方式）。

---

## 七、常见问题

### 打开 localhost:5173 黑屏 / 连不上

按顺序排查：

1. **服务活着吗**：`cd web && .\start.ps1` 重启（会自动清端口）。Vite 是前台进程，启动它的终端关了服务就没了——这是最常见原因
2. **浏览器缓存了旧版 JS**：`Ctrl + F5` 强制刷新
3. **还是黑屏**：页面现在有 ErrorBoundary，崩溃会显示错误文字而不是黑屏；按 F12 看 Console，把报错发我

### 启动脚本报错

`start.ps1` 用了三层回退定位仓库根（参数 → 脚本位置 → 向上找 AGENTS.md）。如果报"无法定位仓库根"，在仓库目录内运行，或显式指定：

```powershell
.\start.ps1 -RepoRoot <仓库目录>
```

### npm 命令没反应

Windows 下手动启动前端必须用 `npm.cmd run dev`。直接 `npm run dev` 在某些调用方式下会静默失败（无报错、端口不监听）。

### 端口被占用

`start.ps1` 会自动释放 8765/5173。手动释放：

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 网页里岗位卡片没有评分

评分必须满足两点：`解析卡.md` 存在 **且** 四项加总与总分自洽（会被 `jd_score` 规则校验）。如果手改过解析卡导致格式不对，网页会当作"未评分"。用 `python tools/jd_score.py <解析卡路径>` 看具体哪里不自洽。

### CSV 用 Excel 打开乱码

不会乱码——写入用了 UTF-8 BOM（`utf-8-sig`）。如果乱码，说明文件被其他工具重写过编码，联系我修复。

### 英语相关（个人红线）

档案红线：CET-6 实际未通过（415），任何材料**不得出现** CET-6/六级/英语良好；简历外语栏只写 CET-4（444）；JD 要求 CET-6 时硬门槛直接 fail。

---

## 八、技术文档导航

| 想了解 | 看哪份 |
|---|---|
| 整体架构（三层分离、领域插件） | `docs/specs/2026-08-30-general-workbench-design.md` |
| Web 层设计（API 契约、并发与安全） | `docs/specs/2026-08-30-web-prototype-design.md` |
| AI 工作流定义 | `.codebuddy/skills/` 下五个 SKILL.md |
| 文档总索引 | `docs/README.md` |
