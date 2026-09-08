---
name: resume
description: Use when 用户改完简历内容后需要重新生成 PDF、校验简历页数与文本层、排查 ATS 抓取问题，或要更换简历照片时。
---

# 重建简历 PDF 并校验

单独运行 PDF 流水线，不经过 JD 解析。用于改完简历后的回归验证。

## 用法

```
python tools/resume_build.py                      # 全部版本都生成并校验
python tools/resume_build.py --version hvac       # 只生成指定版本
python tools/resume_build.py --no-verify          # 只生成不校验

# 数据驱动「标准版式」：JSON + 内置模板（不经过手写 HTML）
python tools/resume_build.py render                          # 全部 JSON 版本
python tools/resume_build.py render --version hvac           # 只生成指定 JSON 版本
python tools/resume_build.py render --version hvac --no-verify
```

省略 `--workspace` 时默认使用 `personal/`。

## 前提

**两条路径并存，先确认走哪条：**

| 路径 | 生成源 | 命令 | 适用 |
|---|---|---|---|
| 高级模板 | 手写 HTML `02_简历工坊/pdf/resume_<版本>.html` | 无子命令 | 精排版式（如 v1.2 色彩版） |
| 标准版式 | JSON 数据 `02_简历工坊/source/resume_<版本>.json` | `render` 子命令 | 可复用、按 JD 裁剪、Web 编辑 |

手写 HTML 路径：**生成源是 HTML 模板**，不是 Markdown。改简历内容必须同步更新 HTML，否则 PDF 不反映改动。

脚本按 `resume_` 前缀扫描，输出名为 `简历_<版本>.pdf`。新增一个简历版本 = 新增一个 `resume_<版本>.html`（或标准版式下新增 `source/resume_<版本>.json`），无需改任何代码。

标准版式（`render`）额外断言 PDF 第一页为 A4：内置模板必须显式声明 `@page { size: A4 }`，否则 Chrome 默认 Letter（612×792pt）会破坏一页判定。

照片：覆盖 `02_简历工坊/pdf/photo.jpg`。不需要照片时删除 HTML 中的 `<img class="photo" ...>` 一行。

## ATS 校验三项

1. PDF 页数为 1
2. pypdf 可提取文本 ≥ 300 字符（可用 `--min-text-length` 调整）
3. `config/ats_required_facts.txt` 中的关键事实全部命中（文件不存在时跳过第三项）

三项全过才算成功。失败退出码 1，此时**不得归档投递**。

关键事实清单由用户自定义，通常是最不能删的核心数字与成果。若工作区尚无此文件，提示用户从 `00_事实库/` 整理一份。

## 超页时的删减原则

**先删装饰性内容，绝不删核心成果与可验证数字。**

具体删减顺序应记录在工作区 `AGENTS.md` 的自定义红线中（例如："先删驾驶证与 GPA，绝不删 XX 结果"）。用户档案里没有写时，按此通用原则判断并建议用户补记。

## AI 改写的反编造护栏

Web 端「简历工坊 → AI 改写」生成建议时，反编造条款（`web/backend/resume_guard.py` 的 `GUARDRAIL_CLAUSE`）由测试锁死——**删句即 `tests/test_prompt_guardrails.py` 失败**。任何改写能力（CLI 或 Web）必须遵守同样的条款：

1. 只改写既有事实的表述，**不新增任何事实**；
2. 不新增原文没有的数字、百分比、金额、规模、时长；
3. 不增删段落条目，不动身份字段（姓名/电话/邮箱/地点）；
4. 每处改写都要经得起面试五到十分钟的追问。

本地校验器五项（空改动 / 结构漂移 / 身份字段 / 字数爆炸 / 新增数字）未通过的建议**不得静默落盘**——必须标红列出问题，用户显式确认后才可采用。CLI 侧给用户改简历时同样执行此标准。
