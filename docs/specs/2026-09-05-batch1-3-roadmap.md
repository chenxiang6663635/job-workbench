# 第一批–第三批实施：设计与验收记录

日期：2026-09-05 起
前置：P0–P3 四批已全部落地（见 `2026-09-03-p0-p3-roadmap.md`）
来源：投递闭环后剩下的两类空白——**数据录入靠手敲**（简历、追踪表）、**产出只有 PDF**（网申系统要文本）

## 总原则

- **分三批、每批独立可验收**，一批做完跑完整验证交用户确认，随时可停
- 严守 6 个脚本上限：新能力一律落在既有脚本子命令或既有路由
- **不引入任何新运行时依赖**：PDF 用已有 `pypdf`，docx 用标准库 `zipfile` + XML，模型走既有 BYOK
- 诚实红线贯穿三批：简历导入是「**抽取**」不是「生成」，缺失留空、严禁补全

## 第一批 · 导入与导出闭环（已落地）

| 能力 | 落点 | 要点 |
|---|---|---|
| 简历一键导入 | `web/backend/resume_import.py` + `POST /api/resume/import` + `ResumeImportDialog.tsx` | PDF（pypdf）/docx（zip+XML）/md/txt 抽取文本 → BYOK 结构化 → **可溯源校验** → 核对页（未抽到标黄、疑似补全标红）→ 确认后才走既有 PUT 落盘 |
| 导入红线条款 | `resume_import.IMPORT_CLAUSE` + `tests/test_prompt_guardrails.py` | 与 `GUARDRAIL_CLAUSE` 同等地位，测试锁死（删句即失败）；条款四要点：只抽取 / 缺失留空 / 禁止补全推测 / 禁止美化数字 |
| 可溯源校验 | `resume_import.traceable_issues()` | 字段值归一化（去空白 + 全角转半角）后必须是原文子串，数字必须来自原文；不在原文中的列为「疑似模型补全，请核对」 |
| 追踪表 CSV 批量导入 | `tracker.py import` 子命令 + `parse_import_csv`/`preview_import`/`commit_import` + `POST /api/applications/import` | 两阶段：preview 只读出差异表，commit 才写入；提交持 `tracker.lock` 并重校验，冲突整批拒绝（返回 -1），绝不半批写入 |
| 导入预校验 | `tracker._validate_import_row()` | 必填（公司/岗位/方向/批次/阶段）、日期格式、阶段与批次与来源枚举、评分 0–100、终态必填原因、方向校验；产出 `ok`/`duplicate`（既有非终态或同批重复，可跳过）/`error` 三态并给出行号与原因 |
| 导出 Word | `GET /api/resume/{version}/doc` | 复用 `render_block` 渲染链路产出 HTML，补 Word 兼容头与 `meta charset`，`application/msword` 返回；**零依赖**，文件名走 RFC 5987 带中文名 |

### 关键取舍

- **导入端点绝不落盘**：只返回 `{text, data, issues, unfilled}`，写入必须经核对页逐段确认后走既有 PUT。没有「一键直接落盘」的捷径——这一页是诚实红线的物理载体
- **duplicate 不是 error**：同公司+岗位既有记录非终态 → 跳过（避免重复投递）；既有记录已终态 → 放行（挂了可以再投一次）
- **Word 版定位是「文本搬运」**：排版以 PDF 为准，按钮旁固定标注「Word 版只保证文本可复制」，绝不让用户误当正式交付物
- **隐私**：上传文件只落在系统临时目录，用完 `shutil.rmtree` 即删，不进工作区、不进快照、不进 git

## 第二批 · 面试与推进增强（待实施）

| 能力 | 落点 | 要点 |
|---|---|---|
| 面试题库 | `GET /api/progress/question-bank` + `QuestionBank.tsx`（进展页第四个子 Tab） | 按公司+岗位聚合 `interviews.csv` 的问题记录/我的回答要点/复盘；支持关键词检索；纯只读，不做聚类（YAGNI） |
| 投递健康度 | `tracker.health_score()` + `SORTS` 增加 `health` + 行内徽章 | 四态：**urgent**（非终态且距截止 ≤3 天仍未投）/ **overdue**（下次动作日期已过期）/ **stale**（停留超 `STALE_DAYS`）/ **ok**；终态不参与判定。**给理由不给黑箱分数** |
| 看板待推进 | Dashboard 新增清单卡 | urgent + overdue 条目，点击下钻到追踪表并预置健康度排序 |

## 第三批 · 长期资产（可裁剪，待实施）

| 能力 | 落点 | 要点 |
|---|---|---|
| 失败原因聚类 | `report.retrospective()` 增加 `failureClusters` | 按 `config/failure_keywords.txt` 可维护关键词表聚合高频原因；缺省退化为「状态原因」频次统计；样本不足时明确「样本太少，暂不展示」 |
| JD 链接抓取 | `POST /api/jobs/fetch-jd` | urllib 抓取 + 正则去标签取正文存 `JD原文.md`；抓取失败或正文过短明确降级提示手动粘贴，不假装成功 |

## 验收记录（第一批，2026-09-05）

| 检查 | 结果 |
|---|---|
| `pytest tests/`（护栏 23 项，含导入条款 4 项 + 可溯源校验 5 项 + 抽取 3 项） | 23 passed |
| `tracker.py import --dry-run`（test_ws，含重复行） | 预览表正确：新增 1 / 重复 1，未写入，退出码 0 |
| `tracker.py import`（同文件，真提交） | 写入 1 条 + 时间线入账，退出码 0；重复行跳过 |
| CLI 空文件 / 缺列 | 明确报错「CSV 内容为空」，退出码 1 |
| 前端 `npm run build` | exit 0 |
| API 冒烟：preview / 错误行 commit / 正常 commit / Word 导出 | 200（counts 正确）/ 422「存在 1 个错误行，修正后才能提交」/ 200 written=1 / 200 + `application/msword` + 中文文件名 |
| Playwright 端到端 | 弹窗三类分色徽章与行号原因正确；有错误行时「确认导入」禁用；干净 CSV 提交后弹窗关闭且列表出现新记录（重复行跳过）；Word 链接 title 与 href 正确，实际取回 200 + `meta charset` + 中文文件名；导入核对页红线文案齐备且**未出现保存按钮**；模型端点不可用时 502「连不上模型端点：…」而非 500 |

## 遗留与注意

- **浏览器缓存**：前端改动后需强刷（`main.py` 已加缓存中间件：HTML `no-cache`、assets `immutable`）
- **端到端测试端口**：8765 曾被上一会话遗留的旧服务占用（旧代码无 `/import` 路由，表现为 405），验证前需确认监听进程为新代码
- 第二批/第三批按上述设计推进，每批结束跑同一套验收并交用户确认
