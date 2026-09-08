# 开源发布准备：设计与执行清单

日期：2026-09-07
目标：把「求职工作台」以 MIT 协议发布到 GitHub，公开前彻底清除真实个人数据
前置：三批功能（P0–P3 + 第一批/第二批/第三批）已全部落地并验收

## 一、现状审计结论（2026-09-07 实测）

| 项 | 状态 | 说明 |
|---|---|---|
| LICENSE | 缺失 | GitHub 默认「保留所有权利」，必须补 |
| `personal/` 入库 | **107 个文件** | `.gitignore` 只挡住 `source/*.json` / `pdf/*.pdf` / `photo.jpg`，其余全在版本库 |
| ├ `05_投递追踪/tracker.csv` | 敏感 | 真实投递记录（公司/岗位/评分/状态原因/备注） |
| ├ `02_简历工坊/简历_*.md`、`pdf/*.html` | 敏感 | 命中 4 处手机号与邮箱 |
| ├ `00_事实库/*事实卡*`、`01_岗位池/<真实公司>_*` | 敏感 | 真实公司与项目细节 |
| └ `personal/AGENTS.md` | 敏感 | 硬门槛事实（学校/学历/届数/城市） |
| git 历史 | **含上述文件** | 只删文件无效，必须清洗历史 |
| 提交身份 | `cx <cx@local>` | 本机假邮箱，无真实邮箱泄露；发布前改为公开身份 |
| 远端 | **无** | 首次公开，清洗后直接推新仓库，无 force-push 波及他人风险 |
| 工作区发现机制 | 只扫仓库根 | `workspace_root = ROOT`、`allowed_roots = [ROOT]`，工作区不能移到库外 |
| 已忽略项 | 合格 | `test_ws/`、`research_*.md`、`.codebuddy/memory/`、`quarantine/` |
| `.github/` | 仅 ISSUE_TEMPLATE | 缺 LICENSE、CI、PR 模板、行为准则 |
| 版本/tag | 未打 tag | CHANGELOG 全部归 Unreleased；版本号来源 `web/electron/package.json` |
| 依赖许可证 | 宽松 | FastAPI(MIT)、pypdf(BSD)、recharts(MIT)、lucide(ISC)、Electron(MIT)，无 GPL 传染 |
| 后端监听地址 | ✅ 已复核 | `main.py` 默认 `--host 127.0.0.1`、CORS 限 localhost，已写入文档 |

## 二、决策

| 决策 | 选择 | 理由 |
|---|---|---|
| 开源形态 | **整体开源 + 清洗历史** | 代码/template/docs 全公开，价值最大；真实数据仅存在于本地与历史中，清除即可 |
| 许可证 | **MIT** | 最宽松、易被采用；依赖也都是宽松许可 |
| 版权人 | **`job-workbench contributors`** | 不暴露真实身份，便于后续贡献者参与 |
| 真实工作区 | **留在磁盘原位的 `personal/`** | 工作区发现只扫仓库根，移出去工具就找不到；用 `.gitignore` + 历史清洗实现「库里没有、本地照用」 |
| 库外工作区支持 | **不做** | 需改 `pathres`/`deps`/打包逻辑，收益不抵风险（YAGNI） |

## 三、执行步骤（分五批，每批可独立停下）

### 批次 A · 备份与扫描（无风险，先做）

1. `git clone --mirror` 到仓库外（如 `D:\backup\job-workbench.git.mirror`）
2. 复制一份 `personal/` 到仓库外（双保险）
3. 全量扫描敏感面：手机号/邮箱/密钥（`sk-`）/本机绝对路径，覆盖工作区与**全部 git 历史 blob**
4. 输出扫描报告，作为清洗后的对照基线

### 批次 B · 隐私护栏（无风险）

1. `.gitignore` 整体忽略 `personal/`（保留既有规则：`*.lock`、`test_ws/`、`.jobws_tmp_*` 等）
2. 提交身份改为公开身份（`git config user.name/email`，历史改写时一并替换）
3. `README.md` 与 `CONTRIBUTING.md` 增加隐私条款：本仓库不含任何真实数据，贡献时禁止提交 `personal/` 内容
4. 复核 README/文档/截图中的真实公司名与联系方式并脱敏

### 批次 C · 历史清洗（**不可逆，执行前再次确认**）

1. 确认批次 A 的镜像备份可恢复（试着 clone 一份验证）
2. `git filter-repo --path personal/ --invert-paths`（顺带 `--mailmap` 改作者为公开身份）
3. `git reflog expire --expire=now --all && git gc --prune=now --aggressive`
4. 复核：`git log --all --name-only` 无 personal 路径；历史 blob 中无手机号/邮箱命中
5. 本地 `personal/` 必须完好无损（git 忽略不删文件）

### 批次 D · 法务与协作文件

1. `LICENSE`（MIT，版权人 `job-workbench contributors`）
2. `THIRD-PARTY-NOTICES.md`（依赖与许可清单）
3. `.github/PULL_REQUEST_TEMPLATE.md`、`CODE_OF_CONDUCT.md`
4. CI：`.github/workflows/ci.yml` —— pytest（33 项护栏）+ 前端 `npm run build` 作为质量门
5. 复核后端默认监听地址只绑 `127.0.0.1` 并写入文档

### 批次 E · 发布

1. CHANGELOG 的 Unreleased 转为 `0.1.0` 并标注日期
2. 版本号对齐 `web/electron/package.json`，打 tag `v0.1.0`
3. 创建 GitHub 仓库（公开），首次推送
4. Release 说明：定位、安装启动、隐私声明（本仓库不含真实数据）、贡献指引

## 四、验收清单

| 检查 | 通过标准 |
|---|---|
| 历史扫描 | 全部 commit 与 blob 中无 `personal/` 路径、无手机号/邮箱/密钥 |
| 工作区完整性 | 本地 `personal/` 文件数与清洗前一致，CLI 与 Web 仍能正常读写 |
| 功能回归 | `pytest` 33 项通过；`npm run build` 通过；本地启动后四页面可用 |
| 法务文件 | LICENSE / NOTICES / PR 模板 / CoC 就位；CI 在干净环境跑通 |
| 版本 | CHANGELOG 有 `0.1.0` 条目；tag 已打；远端可见 |

## 五、风险与回退

- **清洗不可逆**：批次 C 前必须完成镜像备份并验证可 clone；备份缺失则不执行
- **清洗误伤**：`filter-repo --path personal/` 只删该前缀，其他路径不动；执行前后用 `git ls-files` 数量对比核对
- **本地数据不受影响**：`.gitignore` 与历史清洗都不删磁盘文件，最坏情况不过是重新 `git init`
- **身份泄露残余**：若历史其他地方（如 research 报告、截图）含个人信息，批次 A 的扫描会列出，逐项处理后再清洗
