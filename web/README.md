# Web 界面

浏览器界面（及桌面壳后端），与 CLI 共享同一份 Markdown + CSV 数据源。在网页里新增的记录，CLI 同样能读到，`git diff` 同样能看到。

## 启动（开发模式，前后端分离）

**终端一：后端**

```bash
cd web/backend
pip install -r requirements.txt
python -m uvicorn main:app --port 8765
```

**终端二：前端**

```bash
cd web/frontend
npm install
npm run dev
```

打开 http://localhost:5173 。后端未启动时页面顶部会显示「后端未启动」并给出启动命令。

**一键启动**：仓库根执行 `powershell -ExecutionPolicy Bypass -File web/start.ps1`，自动起前后端 + 打开浏览器。

**双击 exe（免环境）**：构建产物在 `web/backend/dist/job-workbench-backend/`，双击 `job-workbench-backend.exe` 自动起服务并开浏览器。exe 是**干净分发物**（数据在 exe 旁空工作区），自用请走上面开发模式。重新构建：`scripts/build_backend_exe.ps1`。

## 七个页面

| 页面 | 内容 |
|---|---|
| 看板 | 投递漏斗、按方向/批次统计、近七天待办（可一键顺延 7 天）、已过截止日提醒、静默提醒（长期无进展）、**待推进**（健康度异常清单，可下钻）、**周期复盘**（阶段转化率 / 停留中位天数 / 失败归因 / **失败原因聚类**）。统计卡与漏斗/方向/批次均可点击下钻到追踪表 |
| 追踪表 | 投递记录列表，按阶段/方向/批次筛选 + 关键字搜索 + 排序（含**健康度**），行内改阶段与「状态原因」，新增投递（含终态不回退/去重/原因必填约束，「我拒绝的 offer」为双向选择终态），**CSV 批量导入**（预览差异表，新增/重复/错误分色，有错误禁提交），行展开查看变更时间线与停留天数 |
| 岗位池 | 岗位卡片（含评分与档位）、新建岗位粘贴 JD 或**从链接抓取正文**（抓不到会明确提示手动粘贴，不留空壳）、详情页（资格硬门槛置顶 + 评分四维下钻 + 证据标签 + **简历差距面板**：可召回 / 真实缺口二分） |
| 简历工坊 | **双模式**：「标准版式」= 数据驱动编辑（左结构化表单、右 A4 实时预览、生成 PDF + ATS 校验、防超页护栏，页面上直接新建版本）+ **一键导入**（PDF/Word/MD/TXT 抽取 → 核对页逐段确认才落盘）+ **AI 改写建议**（反编造校验不过不能采用）+ **导出 Word**（零依赖，只保证文本可复制，排版以 PDF 为准）；「高级模板」= 手写 HTML 精排版的只读浏览与一键生成；底部**版本谱系**（该版本投了哪些岗位） |
| 进展 | 投递之后的主战场，四个子 Tab：**面试**（三段式复盘记录 + 导出 `.ics` 日程）、**题库**（按公司归集被问过的问题与自己的回答，可关键词检索）、**联系人**（跟进节奏管理，超期琥珀提醒）、**Offer 对比**（只并排已知事实，绝不给建议） |
| 素材库 | 事实库浏览（简历文件已迁往简历工坊，避免同名混淆） |
| 设置 | Provider（BYOK）：base_url/key（脱敏）/ 测试连接；**数据与隐私**：整包导出 zip / 立即快照备份 / 打开数据目录 / 无遥测声明 |

导航栏可切换工作区（默认 personal），选择会记住（localStorage），各请求携带工作区参数。

## 与 CLI 的关系

Web 只是同一份文件的另一个视图：

- 数据都在 `personal/` 下，Web 不复制、不缓存
- 在网页新增投递 → `python tools/tracker.py --workspace personal list` 能查到
- 用 CLI 或 AI 生成的解析卡 → 岗位池详情页自动展示四维度评分与档位
- 所有改动都能被 `git diff` 追踪

**评分不在网页里做。** JD 解析评分由 AI 在 AI CLI 中完成（jd 工作流），写入 `解析卡.md` 后网页读取展示。网页只提供查看与下钻，不做评分决策。

## 技术栈

后端 FastAPI（Python 3.8 兼容，直接 import `tools/` 下现有脚本，不重复实现业务逻辑）；前端 React + TypeScript + Vite + Tailwind + recharts。

## 目录

```
web/
├── start.ps1                 一键启动（依赖预检/端口/前后端诊断）
├── backend/
│   ├── main.py               FastAPI 入口、CORS、路由挂载、同源托管 dist、双击三态启动
│   ├── pathres.py            路径解析：解包/打包双模式、可写数据目录 fallback
│   ├── deps.py               工作区解析、safe_join 路径安全、数据根
│   ├── filelock.py           跨平台文件锁（防并发写丢数据）
│   ├── atomicio.py           原子写：tmp + os.replace，.jobws_tmp_ 前缀
│   ├── icsutil.py            RFC 5545 日程导出（纯标准库手写）
│   ├── resume_guard.py       反编造条款 + 改写校验器（测试锁死）
│   ├── pyinstaller.spec      PyInstaller onedir 打包配置
│   └── routers/              dashboard / applications / jobs / progress / resume / library / provider / system / workspace
├── electron/                 Electron 桌面壳（探测打包 exe → spawn → 开窗 → 退出杀进程树）
└── frontend/
    └── src/
        ├── api.ts            API 客户端与类型（全局工作区状态）
        ├── App.tsx           导航壳、后端连接状态、工作区切换下拉
        ├── components/       InterviewList / QuestionBank / ContactList / OfferCompare / GapPanel / RewritePanel / VersionLineage / RetrospectivePanel / ResumeForm / ResumeTemplates / ResumeImportDialog / ImportApplicationsDialog / InterviewForm / OfferForm
        └── pages/            Dashboard / Applications / Jobs / Resume / Progress / Library / Settings
```

仓库根 `tests/` 共 33 项测试（反编造护栏 + 健康度语义）由 CI（`.github/workflows/ci.yml`）与本地 `python -m pytest tests/ -q` 把关；后端依赖见 `backend/requirements-dev.txt`。

## 已知边界

- 仅本地单用户（无账号登录），以 workspace 目录隔离代替用户隔离
- 自动更新不做（剩余阻碍是 macOS 代码签名），分发走手动安装包
- 简历的可视化在线编辑未纳入：结构化字段用表单改，精排版仍走手写 HTML
