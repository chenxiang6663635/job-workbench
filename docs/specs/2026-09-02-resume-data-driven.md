# 简历数据驱动改造：schema 与渲染契约（2026-09-02）

## 路线（用户已确认 A）

**数据驱动只服务一份"标准版式"**，作为可复用、面向普通用户的版式；现有 personal 的
`resume_hvac.html`/`resume_datacenter.html`（v1.2 色彩精排版）**保留不动**，继续走
"手写 HTML → Chrome 打印"老路（高级模板）。两条路径并存：
- 高级模板（现有手写 HTML）：`tools/resume_build.py --workspace X --version <版本>` 直接打 HTML
- 标准版式（数据驱动）：`tools/resume_build.py render --workspace X --version <版本>`，JSON → 内置模板 → HTML → 打印

不损失现有外观；工作量为中。

## 一、数据文件：`02_简历工坊/source/resume_<版本>.json`

版本 slug 沿用 HTML 命名惯例（`resume_hvac.json` 对应 hvac）。JSON 是 JSON Resume 风格的**精简子集**，
标准库 `json` 解析（Python 3.8），AI/人/Web 编辑器三方都读写同一份。

```jsonc
{
  "meta": {
    "intent": "求职意向一句话",
    "profile": "两到三句个人概况（可留空，渲染时省略该区块）"
  },
  "basics": { "name": "姓名", "phone": "", "email": "", "location": "" },
  "education": [
    { "school": "", "major": "", "degree": "", "period": "", "note": "" }
  ],
  "projects": [
    {
      "title": "", "tag": "（如 SCI 二区 TOP · 第二作者）",
      "points": ["做了什么 + 方法 + 可验证结果", "…"]
    }
  ],
  "work": [
    { "org": "", "role": "", "period": "", "points": ["…"] }
  ],
  "skills": [ { "group": "暖通 / 制冷", "items": "制冷循环与 COP、…" } ],
  "extras": {
    "research": ["已发表（SCI…）：…", "…"],
    "awards": "2025 硕士国家奖学金；…",
    "certificates": "CET-4；…"
  }
}
```

字段说明（诚实红线约束）：
- `projects[*].points` 每一条是一个经得起追问的完整句子（主语是你做的事，不是项目做的事）
- `basics` 只放必要联系方式；姓名/联系方式属个人事实，个人填写、不放模板
- `meta.profile` 为空时整块省略（防空白区块占版面）
- `extras` 的 research/awards/certificates 各自独立，便于按 JD 增删

## 二、内置模板：`template/workspace/02_简历工坊/templates/std_resume.html`

- **必须是显式 `@page { size: A4; margin: ... }`**（实测：不声明默认 Letter 612×792，声明 A4 才 594.96×841.92）
- 标准库渲染，不引第三方模板引擎——用最小占位符替换，避免依赖注入（3.8 环境无 jinja）
- 版式走规整单栏（技能/奖项等非多栏，保 ATS 阅读顺序），中文字体栈 `"Microsoft YaHei","微软雅黑","SimSun",sans-serif`
- 区块由 JSON 字段有无驱动（profile 空则无 profile 区块），项目 bullet 逐条渲染
- 文字全真实文本，不用图片/canvas

## 三、`resume_build.py` 子命令接口

向后兼容约束：现有无子命令入口（`--version/--out/--no-verify`）行为不变。
新增：
```
python tools/resume_build.py render --workspace <WS> --version <版本> [--out DIR] [--no-verify]
```
- 读 `<WS>/02_简历工坊/source/resume_<版本>.json` → 渲染成临时 HTML → 走既有 build_pdf/verify_pdf
- 校验三项沿用既有（页数 1 / 文本 ≥ 阈值 / ats_required_facts 命中）
- `render` 不含 `--version` 时扫 source/ 下所有 `resume_*.json` 全量渲染
- 内部渲染函数独立成模块级 `render_to_html(data, template_html)`，供 Web 后端后续复用

## 四、与现有能力的边界（避免误改）

- `resume_build.py` **无任何程序化 import**（code-explorer 全量检索确认），全是 CLI 文档引用，
  加 `render` 子命令不破坏现有调用
- 文档引用 7 处（README:102、usage-guide:180-203、skills/resume、skills/apply + .codebuddy 副本）：
  新增 render 时**只追加不删除**，老命令示例保留
- `discover_jobs` 输出名规则 `简历_<stem>.pdf`；render 输出名沿用 `简历_<版本>.pdf`（写 source/ 同 slug 目录下的 pdf/ 同侧，避免与手写 HTML 同名冲突时覆盖既有 v1.2）

## 五、Web 编辑（已随本批完成；信息架构 2026-09-03 调整）

简历工坊页（Web）已随本批落地，并在用户反馈同名混淆后做了信息架构调整（方案 3，双模式页面）：

- 后端 `web/backend/routers/resume.py`：`GET/PUT /{version}`、`GET /{version}/html`（预览）、
  `POST /{version}/build`（生成 + ATS 三项 + A4 纸型）。复用 `resume_build` 的函数，
  `verify_pdf` 通过显式 `facts_file` 参数规避模块级全局在 Web 并发下互相覆盖的问题。
- **双模式页面**（顶部切换，`pages/Resume.tsx`）：
  - **标准版式**：数据驱动编辑——左结构化表单（`components/ResumeForm.tsx`）、右 A4 实时预览
    （ResizeObserver 测 794×1123 溢出）；超一页时琥珀色提示 + 禁用生成；生成后回显
    纸型/页数/文本/关键事实四项；诚实红线常驻提示。支持**页面上直接新建版本**
    （输入版本名 → 后端写空模板 JSON → 进入编辑），不再要求用户手工去文件系统放 JSON。
  - **高级模板**：手写 HTML 精排版的**只读浏览与一键生成**（`components/ResumeTemplates.tsx`）。
    文件浏览能力自素材库迁入（`/api/resume/templates`、`/templates/content`、
    `/templates/file/{rel:path}`——路径式端点使 iframe 内 HTML 的相对资源 photo.jpg 可解析；
    `/templates/{version}/build` 复用 build_pdf/verify_pdf）。编辑仍走手写 HTML / CLI。
- **素材库只保留事实库**：`library.py` 删除 resumes 分支（404），`Library.tsx` 移除入口并提示
  "简历文件已迁往简历工坊"。此前素材库的「简历工坊」分类与新 Tab 同名异物，是用户困惑的根源。
- **路由顺序注意**：`GET /templates` 等具体路由必须注册在 `GET /{version}` 之前，
  否则动态参数路由会把 "templates" 抢先匹配成 version。
- **编辑写回安全**：预览 effect 以 `dirty` 标记区分「刚加载」与「用户已编辑」，仅编辑后才自动
  保存（防止加载即写回覆盖用户数据，schema 演进时未表达字段会被写丢）。
- 标准版式内置模板实际实现为 `template/workspace/02_简历工坊/templates/std_resume.html`，
  渲染函数为 `resume_build.render_block` / `_profile_block` 等系列，schema 各字段一一对应。

## 验收

- `resume_build.py render --workspace <WS> --version hvac` 产出 A4 一页 PDF 且 ATS 三项通过
- 模板不声明 @page 时若误产 Letter，应能通过 mediabox 校验发现（render 后回读 page[0].mediabox 断言 A4）
- Python 3.8 兼容、只用标准库
