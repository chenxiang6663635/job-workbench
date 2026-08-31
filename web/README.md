# Web 界面（本地原型）

浏览器界面，与 CLI 共享同一份 Markdown + CSV 数据源。在网页里新增的记录，CLI 同样能读到，`git diff` 同样能看到。

## 启动

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

## 三个页面

| 页面 | 内容 |
|---|---|
| 看板 | 投递漏斗、按方向/批次统计、近七天待办、已过截止日提醒 |
| 追踪表 | 投递记录列表，按阶段/方向/批次筛选，行内改阶段与下次动作，新增投递 |
| 岗位池 | 岗位卡片（含评分与档位）、新建岗位粘贴 JD、详情页左右分栏看 JD 与解析卡 |

## 与 CLI 的关系

Web 只是同一份文件的另一个视图：

- 数据都在 `personal/` 下，Web 不复制、不缓存
- 在网页新增投递 → `python tools/tracker.py --workspace personal list` 能查到
- 用 CLI 或 AI 生成的解析卡 → 岗位池详情页自动展示四维度评分与档位
- 所有改动都能被 `git diff` 追踪

**评分不在网页里做。** JD 解析评分由 AI 在 CodeBuddy 中完成（jd 工作流），写入 `解析卡.md` 后网页读取展示。网页只提供查看，不做评分决策。

## 技术栈

后端 FastAPI（Python 3.8 兼容，直接 import `tools/` 下现有脚本，不重复实现业务逻辑）；前端 React + TypeScript + Vite + Tailwind + recharts。

## 目录

```
web/
├── backend/
│   ├── main.py              入口：CORS、路由挂载
│   ├── deps.py              工作区解析、safe_join 路径安全
│   ├── filelock.py          跨平台文件锁（防并发写丢数据）
│   └── routers/             dashboard / applications / jobs
└── frontend/
    └── src/
        ├── api.ts           API 客户端与类型
        ├── App.tsx          导航壳与后端连接状态
        └── pages/           Dashboard / Applications / Jobs
```

## 已知边界

- 仅本地单用户，无登录与用户隔离
- 不做打包分发（原型阶段，确认好用后再决定形态）
- 简历 PDF 生成页面未纳入本批次
