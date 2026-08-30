---
name: resume
description: Use when 用户改完简历内容后需要重新生成 PDF、校验简历页数与文本层、排查 ATS 抓取问题，或要更换简历照片时。
---

# 重建简历 PDF 并校验

单独运行 PDF 流水线，不经过 JD 解析。用于改完简历后的回归验证。

## 用法

```
python tools/resume_build.py                    # 两版都生成并校验
python tools/resume_build.py --version hvac     # 只生成 HVAC 版
python tools/resume_build.py --no-verify        # 只生成不校验
```

## 当前基线

v1.2 色块版：`某用户_简历_空调制冷HVAC_v1.2色块版.pdf`、`某用户_简历_数据中心冷却_v1.2色块版.pdf`。

**生成源是 HTML 模板**（`02_简历工坊/pdf/resume_hvac.html`、`resume_datacenter.html`），不是 Markdown。改简历内容必须同步更新 HTML，否则 PDF 不反映改动。

同目录 `_v1.0.pdf` 与 `_v1.1.pdf` 为历史存档，保留但不使用。

## ATS 校验三项

1. PDF 页数为 1
2. pypdf 可提取文本 ≥ 800 字符
3. `config/ats_required_facts.txt` 中 18 项关键事实全部命中

三项全过才算成功。失败退出码 1，此时**不得归档投递**。

## 超页时的删减顺序

驾驶证 → 本科 GPA/部分课程 → Profile 压一行 → 项目1方法细节 → 标准栏。

**绝不先删**：X% 结果、控制贡献、SCI、硕士课程成绩、工程实践。

## 换照片

覆盖 `02_简历工坊/pdf/photo.jpg`（一寸照比例，24mm × 33.6mm）。不需要照片时删除 HTML 中的 `<img class="photo" ...>` 一行。
