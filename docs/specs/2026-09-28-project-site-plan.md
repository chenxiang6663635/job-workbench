# 项目官网（docs site）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 上线一个国内可访问的项目文档站（介绍 + 使用手册 + 下载），内容单源（docs/ 组装），零自费。

**Architecture:** GitHub Actions 组装（build_site.py：白名单复制 + 模板注入 + 链接重写）→ `mkdocs build --strict` → 产物推 `site-dist` 分支 → EdgeOne Makers 零构建分发。

**Tech Stack:** Python 3.12 / pytest；MkDocs + Material + mkdocs-static-i18n（pin 版本）；GitHub Actions。

**Spec:** `docs/specs/2026-09-28-project-site-design.md`

## Global Constraints

- 一切走 PR（分支 `docs/site`），Conventional 提交且 subject 含中文；squash 合并。
- 不碰产品代码（只新增 `tests/test_build_site.py`；其余改动限 site/ 与文档/CI）。
- 零自费：任何环节不得引入付费服务；站上零遥测/统计。
- `site/` 纳入 `jobws lint size` 水位纪律（≤300 行/文件）。
- 依赖 pin：`site/requirements.txt` 记录实施时安装的精确版本。
- 站点默认语言中文；英文以「源文件存在」为准（index / usage-guide）。
- `site/.build/` 入 `.gitignore`。

## Review Focus

1. **白名单泄漏**：docs/ 中任何未列白名单的文件（含将来新增）绝不进产物 → Task 1 测试。
2. **版本漂移**：版本号/日期一律来自 package.json 与 CHANGELOG（模板占位符，无硬编码）→ Task 1 测试。
3. **坏链**：站内链接失败即构建失败（--strict）→ Task 2/5 验证步。
4. **i18n 回退**：英文缺页回退中文且导航不碎 → Task 2 配置 + Task 5 手动检查。
5. **site-dist 污染**：产物分支只含构建产物（仅从 `.build/site` 推）→ Task 3 验证步。

---

### Task 1: 组装器 build_site.py + 单元测试

**Files:**
- Create: `site/scripts/build_site.py`、`tests/test_build_site.py`、`site/requirements.txt`
- Modify: `.gitignore`（加 `site/.build/`）

**Interfaces（Task 2-6 依赖）:**
- `parse_version(package_json_text: str) -> str`；`parse_release_date(changelog_text: str) -> str`（无 `- 日期` 回退空串）
- `render_template(text: str, *, version: str, release_date: str) -> str`（替换 `{{VERSION}}` / `{{RELEASE_DATE}}`）
- `rewrite_links(text: str, *, source: str) -> str`（四规则，见下）
- `assemble(repo_root: Path, out_dir: Path) -> None`；CLI `python site/scripts/build_site.py`（默认输出 `site/.build/docs/`）

**白名单（唯一允许进产物的映射，正列）:**
```
site/content/**.tmpl.md            → 去 .tmpl、注占位符 → /
docs/usage-guide.zh-CN.md          → manual/guide.md
docs/usage-guide.md                → manual/guide.en.md
docs/data-flow-matrix.md           → privacy/index.md
docs/support-and-compatibility.md  → compat/index.md
docs/screenshots/*.png, zh-CN/*.png → assets/screenshots/（保子目录）
```

**链接重写四规则（对组装进来的 md）:**
1. 指向白名单内文档 → 站点相对路径（如 `manual/guide.md`）
2. 其余相对 `*.md` 链接（含 `../README.md` 等仓库文件）→ `https://github.com/chenxiang6663635/job-workbench/blob/main/<仓库内路径>`
3. `screenshots/...` 图片引用 → `assets/screenshots/...`
4. 其余（外链、锚点）不动

- [ ] Step 1: 写失败测试（tmp_path 假仓库：白名单内外文件、四类链接样例、含/不含占位符）
  必覆盖：四规则各一例 + **白名单外文件不复制**（隐私边界）+ 版本/日期解析
- [ ] Step 2: 运行确认失败（`pytest tests/test_build_site.py -q` → FAIL）
- [ ] Step 3: 实现 build_site.py（argparse；`--repo-root`/`--out` 默认值；结尾一行总结日志）
- [ ] Step 4: `pytest tests/test_build_site.py -q` → PASS；`pytest tests/ -q` 全绿
- [ ] Step 5: `python tools/jobws.py lint size` 通过
- [ ] Step 6: 提交（`feat(site): 站点组装器——白名单复制/模板注入/链接重写 + 单元测试`）

### Task 2: mkdocs.yml + 骨架 + 本地 --strict 构建

**Files:** Create: `site/mkdocs.yml`、`site/content/index.tmpl.md`（最小版）

- [ ] Step 1: mkdocs.yml：`docs_dir: .build/docs`、`site_dir: .build/site`；material 主题（深浅切换、搜索、代码复制）；plugins：search + i18n（`docs_structure: suffix`、`fallback_to_default: true`、zh 默认 / en + nav_translations）；nav 五项；links 校验保持默认（--strict 生效）
- [ ] Step 2: 最小 index.tmpl.md（标题 + 一句话 + `{{VERSION}}`）
- [ ] Step 3: `python site/scripts/build_site.py; python -m mkdocs build -f site/mkdocs.yml --strict` → 成功
- [ ] Step 4: `python -m mkdocs serve -f site/mkdocs.yml` 肉眼（首页 + 语言切换）
- [ ] Step 5: 提交（`feat(site): MkDocs 骨架——中文默认/英文回退 + 严格构建`）

### Task 3: CI workflow site.yml（构建 + site-dist 发布）

**Files:** Create: `.github/workflows/site.yml`

- [ ] Step 1: 两 job 照 release.yml 的读写分离：`build`（PR/push；paths: `site/**`、`docs/**`、`.github/workflows/site.yml`、`web/electron/package.json`、`CHANGELOG.md`；py3.12；`pip install -r site/requirements.txt`；build --strict；`contents: read`）与 `publish`（`needs: build`；仅 main push；在 `site/.build/site` git init 并强制推 `site-dist`；`contents: write`，其余权限空）
- [ ] Step 2: 本分支 push 后 `gh run list --workflow site.yml --limit 3` 绿
- [ ] Step 3: 提交（`ci(site): 站点构建与 site-dist 产物发布`）

### Task 4: 首页正式内容（zh + en）

**Files:** Modify: `site/content/index.tmpl.md`；Create: `site/content/index.en.tmpl.md`

- [ ] Step 1: zh 首页：定位一句话（README「Why」改编）+ 特性 6 条（「Features at a glance」）+ 截图（`assets/screenshots/zh-CN/**`）+ 快速开始 3 行命令（README「Quick start」精简）+ 下载 CTA（站内 `download.md`）+ **Referral 段（照抄 README 同名节，链接不变）**
- [ ] Step 2: en 版（README 英文对应内容 + en 截图）
- [ ] Step 3: build --strict + serve 肉眼（中英切换、截图、链接）
- [ ] Step 4: 提交（`feat(site): 首页（中英）——特性/截图/快速开始/Referral`）

### Task 5: 下载页 + 文档接入 + 导航定稿

**Files:** Modify: `site/mkdocs.yml`；Create: `site/content/download.tmpl.md`（+ `.en.tmpl.md`）；Modify: `docs/release-checklist.md`

- [ ] Step 1: download 页固定文案：最新版本 `{{VERSION}}`（`{{RELEASE_DATE}}`）+ 主下载 GitHub `/releases/latest` + 「国内访问 GitHub 不畅时可在 Issues 留言获取备用链接」+ 未签名/SmartScreen 说明 + `certutil -hashfile` 校验指引
- [ ] Step 2: nav 定稿五项；构建后核对 `manual/guide.md` / `privacy/index.md` / `compat/index.md` 均在产物且可点
- [ ] Step 3: build --strict + serve 逐页肉眼（含英文回退页语言条）
- [ ] Step 4: `docs/release-checklist.md` 增一步：发版后「确认官网下载页版本号（自动）与备用链接」
- [ ] Step 5: 提交（`feat(site): 下载页与文档接入——手册/隐私/兼容 + 发版清单联动`）

### Task 6: 仓库登记 + PR（双轨审查）

**Files:** Modify: `docs/README.md`（索引加 specs 两行）、`CHANGELOG.md`（[Unreleased]）

- [ ] Step 1: doc index 登记 design 与 plan 两份
- [ ] Step 2: CHANGELOG `Added:` 一条（官网 = MkDocs Material 文档站，构建自动化 + site-dist 分发）
- [ ] Step 3: 全量门禁：`pytest tests/ -q` + 五扫描器（lint i18n / ui-tokens / themes / four-ends / size）
- [ ] Step 4: PR（标题含中文）+ Round 1 自审 + Round 2 独立审查 + CI 绿 → squash 合并
- [ ] Step 5: 记忆落档

### Task 7: 合并后——site-dist 上线 + EdgeOne 接入 + 域名验证

- [ ] Step 1: main push 后确认 `site-dist` 分支生成且内容 = 产物（`gh api repos/chenxiang6663635/job-workbench/branches/site-dist`）
- [ ] Step 2: **[用户]** 注册 EdgeOne 国际版（edgeone.ai，邮箱）→ 连接 GitHub 仓库 → 选 `site-dist`、输出目录 `/`、无构建命令 → 部署 → 取默认域名
- [ ] Step 3: 域名打开站点（本机 + 用户侧）；若 Git 集成不支持「监控分支零构建」→ 备选：CI 内 EdgeOne CLI 上传（token 入 Secrets）
- [ ] Step 4: **[用户]** 把域名发给 1-2 个无代理受众实测可达性 → 结论决定是否走 C（域名 + 备案）
- [ ] Step 5: README「Docs」节加官网链接；应用内「打开使用手册」改指在线入口（**单独小 PR**，走产品流程；2026-09-29 落实：按钮先指 Gitee 手册页保国内可达，站点域名落地后再评估回切）
- [ ] Step 6: 记忆落档（上线结果 + 实测结论）
