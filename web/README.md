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

## 六个页面

| 页面 | 内容 |
|---|---|
| 看板 | 投递漏斗、按方向/批次统计、近七天待办（可一键顺延 7 天）、已过截止日提醒、静默提醒（长期无进展）。统计卡与漏斗/方向/批次均可点击下钻到追踪表 |
| 追踪表 | 投递记录列表，按阶段/方向/批次筛选 + 关键字搜索 + 排序，行内改阶段与「状态原因」，新增投递（含终态不回退/去重/原因必填约束），行展开查看变更时间线与停留天数 |
| 岗位池 | 岗位卡片（含评分与档位）、新建岗位粘贴 JD、详情页（资格硬门槛置顶 + 评分四维下钻 + 证据标签） |
| 简历工坊 | **双模式**：「标准版式」= 数据驱动编辑（左结构化表单、右 A4 实时预览、生成 PDF + ATS 校验、防超页护栏，页面上直接新建版本）；「高级模板」= 手写 HTML 精排版的只读浏览与一键生成（原素材库能力迁入） |
| 素材库 | 事实库浏览（简历文件已迁往简历工坊，避免同名混淆） |
| 设置 | Provider（BYOK）：base_url/key（脱敏）/ 测试连接 |

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
│   ├── pyinstaller.spec      PyInstaller onedir 打包配置
│   └── routers/              dashboard / applications / jobs / resume / library / provider / workspace
├── electron/                 Electron 桌面壳（探测打包 exe → spawn → 开窗 → 退出杀进程树）
└── frontend/
    └── src/
        ├── api.ts            API 客户端与类型（全局工作区状态）
        ├── App.tsx           导航壳、后端连接状态、工作区切换下拉
        ├── components/       ResumeForm（简历结构化表单）
        └── pages/            Dashboard / Applications / Jobs / Resume / Library / Settings
```

## 已知边界

- 仅本地单用户（无账号登录），以 workspace 目录隔离代替用户隔离
- 自动更新不可用（需公开远程仓库 + macOS 签名），分发走手动安装包
- 简历 PDF 生成页面未纳入当前批次
