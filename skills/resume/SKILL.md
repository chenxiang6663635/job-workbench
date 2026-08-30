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
```

省略 `--workspace` 时默认使用 `personal/`。

## 前提

**生成源是 HTML 模板**（`02_简历工坊/pdf/resume_<版本>.html`），不是 Markdown。改简历内容必须同步更新 HTML，否则 PDF 不反映改动。

脚本按 `resume_` 前缀扫描模板，输出名为 `简历_<版本>.pdf`。新增一个简历版本 = 新增一个 `resume_<版本>.html`，无需改任何代码。

照片：覆盖 `02_简历工坊/pdf/photo.jpg`。不需要照片时删除 HTML 中的 `<img class="photo" ...>` 一行。

## ATS 校验三项

1. PDF 页数为 1
2. pypdf 可提取文本 ≥ 800 字符
3. `config/ats_required_facts.txt` 中的关键事实全部命中（文件不存在时跳过第三项）

三项全过才算成功。失败退出码 1，此时**不得归档投递**。

关键事实清单由用户自定义，通常是最不能删的核心数字与成果。若工作区尚无此文件，提示用户从 `00_事实库/` 整理一份。

## 超页时的删减原则

**先删装饰性内容，绝不删核心成果与可验证数字。**

具体删减顺序应记录在工作区 `AGENTS.md` 的自定义红线中（例如："先删驾驶证与 GPA，绝不删 XX 结果"）。用户档案里没有写时，按此通用原则判断并建议用户补记。
