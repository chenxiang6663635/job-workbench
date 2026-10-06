# 发布检查清单（Release Checklist）

> 每次打 tag 前过一遍。分两栏：**CI 自动**（release.yml 已固化，绿了就是过了）与
> **人工必做**（必须有人的判断或桌面会话，机器替代不了）。配套阅读：`docs/contributing.zh-CN.md`
> 的「发布流程」七步与「版本号体系」；版本号 = 月粒度 CalVer `YY.MM.N`（`26.9.0`
> 首发 / `26.9.1` hotfix / `26.10.0` 换月）。
>
> 出事了怎么办（RUNBOOK，见第三节）：**撤 latest 标记 → 发一个版本号更高的修复版**
> ——electron-updater 不会接受相同或更低的版本号覆盖，「删掉坏的 Release 重传」无效。
>
> **本轮（v26.10.0）的勾选状态：2026-10-06 记录**。CI 各项与「版本落章」三项已由
> 演练 `37434793050` 与 `release check --tag v26.10.0`（exit 0）验证并勾选；真机与发布
> 那几项已补勾——证据归档在 [`releases/26.10.0-verification.md`](releases/26.10.0-verification.md)
> （#275）。**下一个发布节点请把勾选重置**（清单是可复用的操作单，不是台账）。
> **本批新增**：Release 说明模板重构（`release_notes_format.py`：直链下载置顶 /
> 不重复版本号大标题 / English Highlights 折叠）——下一节点 dry_run 首用；
> 「发布后完整验证链」连续两版未做，下一节点**必须执行**。

## 〇、发布阻断清单（任一存在即不发布）

数据损坏 / 静默覆盖 · secret 泄漏 · 路径越界 · installer 装不上或起不来 · 更新链失效 · 主流程阻断 · privacy 文案与行为不一致 · backup–restore 不可靠。其中四类**不等功能批次**、可直接 `26.10.1` hotfix：安全 / 数据损坏 / 安装·启动阻断 / 更新链失效。完整定义与发布窗口纪律见 docs/contributing.zh-CN.md 的「发布治理」节。

## 一、CI 自动（release.yml，绿了即过）

- [x] 闸 1：tag `v26.10.x` 与 `web/electron/package.json` 的 version **逐字一致** — v26.10.0：演练 `37434793050` 通过（package.json 读为 `26.10.0`）
- [x] 闸 2：CHANGELOG 有同名版本段（抽段即 Release 说明） — v26.10.0：`release check --tag v26.10.0` exit 0（段 77 行）
- [x] 闸 3：产物 exe + `latest.yml` 真实产出（缺 latest.yml 拒发——老用户收不到更新） — v26.10.0：exe 131.6 MB 级 + `latest.yml`（26.10.0 + sha512 + size）已在演练 artifact 内核过
- [x] 后端 exe 冒烟（`scripts/smoke_backend_exe.py`：起产物 → 健康检查） — v26.10.0：演练内步骤通过（起进程 + `/api/system/check` + 资源自检）
- [x] **安装/卸载冒烟**（NSIS `/S` 静默装 → 验证 → 静默卸载；2026-09-24 新增） — v26.10.0：演练内装→验→卸→等目录消失全通过
- [x] **SHA256SUMS.txt** 生成并挂 Release（**完整性**补偿：证明下载未损坏、与已发布文件一致；**不构成发布者身份认证**——未签名场景的身份信任根是 GitHub 账号与仓库保护；也**不能**用于「按 commit 重建校验」——electron-builder 产物非字节可复现，同一个 commit 重跑会得到不同哈希） — v26.10.0：清单已生成，真下载重算 exe 哈希与清单一致
- [x] **SBOM**（`sbom.spdx.json`，Python + npm 两条链）随 Release 挂出 — **v26.10.0 首次勾选**：`release.yml` 固化（生成器 `tools/gen_sbom.py`；零包即构建失败），532 packages 随 Release 与演练 artifact 双处核到；解读见下方「SBOM 怎么用」
- [x] **Release notes 自动附加**未签名 / SmartScreen 说明（微软官方口径：未签名拦截页更严重、每版本信誉归零） — v26.10.0：说明尾部含中英安装说明 + 校验和块；**2026-10-06 起说明模板重构**（直链下载置顶 / 不重复版本号大标题 / English Highlights 折叠，`release_notes_format.py`）
- [x] **发布证明链（全量 E2E）**：`publish` 依赖 `[package, e2e]`——E2E 红则 Release 不会创建（2026-09-25 起的并行结构） — v26.10.0：run `37452235789` 内通过
- [x] 发布后核验资产：exe + blockmap + latest.yml + SHA256SUMS.txt（**v26.10.0 起五样**，含 sbom.spdx.json）全在（**打 tag 后**才做） — v26.10.0：五样齐（见 `releases/26.10.0-verification.md`）

**SBOM 怎么用**（issue #206）：软件物料清单——两条链（`requirements.lock` /
`package-lock.json`）全部包名与版本的机器可读清单，SPDX 2.3 JSON 随 Release 挂出
（`sbom.spdx.json`）。用途：某依赖爆 CVE 时直接对照受影响版本区间，不必重建当时的
依赖树。导入：grype / Dependency-Track 等工具原生可读；临时查一个包用
`jq '.packages[] | select(.name=="fastapi")' sbom.spdx.json` 即可。注意
`licenseDeclared` 一律 `NOASSERTION`——锁文件里没有许可证事实，不猜。

## 二、人工必做（发布日，约 15 分钟 + 真机）

**版本落章**：

- [x] `python tools/jobws.py release version` 取号 → bump `web/electron/package.json`（同一号） — v26.10.0：#272 已落章（package.json / 技能 ×9 metadata / plugin.json 由 `assets_registry --write` 重生成 / CHANGELOG 段名，四处同步）
- [x] CHANGELOG `[Unreleased]` 改为 `[版本号] - ISO 日期` → `release check --tag v<号>` 绿 — v26.10.0：`## [26.10.0] - 2026-10-06`；`release check` exit 0
- [x] dry_run 演练：`gh workflow run release.yml -f dry_run=true -f tag=v<号>` → 下载 artifact 里的安装包 — v26.10.0：`37434793050` success（产物已下载并**四重核验**：artifact digest / 解压六件 / exe sha256 / exe sha512 对照 `latest.yml`）

**真机冒烟**（自己的 Windows 真机，CI 没有桌面会话）：

- [x] **通知实测**：造一条今天到期的待办 → 确认 toast 真的弹出（CI 测不了通知） — v26.10.0：真机通过（dry-run 产物）
- [x] **双开**：第二个实例应直接退出并聚焦已有窗口 — v26.10.0：真机通过（dry-run 产物）
- [x] **离线启动**：断网启动应安静（更新检查失败只进日志，不弹窗） — v26.10.0：真机通过（dry-run 产物）
- [x] 人眼验收四项：八个页面各操作一遍 / 深浅主题各看一遍 / 设置页搜索与单项还原 / 中英切换 — v26.10.0：真机通过（dry-run 产物）
- [x] **DSH preset boot**（D4 遗留，v26.10.0 起纳入）：带 `preset.yml` 的真实 boot——`--dump-config` 零启动合成零警告 + headless 实跑 exit 0；已知边界：headless 无 `agentPresets` 服务，preset 停 pending 属宿主形态（详见 `integrations/dsh/README.md` 待补条）

**发布**：

- [x] `git tag -a v<号> <commit> && git push origin v<号>` → CI 走完 — v26.10.0：tag **annotated** 显式钉在 `0f9cfd8`（真机验证产物的构建提交——同源纪律），run `37452235789` success
- [x] `gh release view` 核资产 → **真下载一次** → 核对 SHA256 — v26.10.0：真下载核验通过（`197fe105…ca954` = `SHA256SUMS.txt`）
- [ ] **发布后完整验证链**（人工至少一次——验的是"用户拿到的东西"，不是本地构建产物）：真下载 → 安装 → 首次启动 → 建工作区 → 打开旧工作区 → 退出 → 再启动 → 卸载（CI 已自动覆盖安装/卸载冒烟；这条是人眼版）——**v26.9.0 / v26.10.0 连续两版未做，下一发布节点必须执行**
- [ ] 发布公告要素：定位一句话 / 隐私承诺（**按 `docs/data-flow-matrix.md` 表述**——不复述"不联网"类绝对句）/ SmartScreen 说明（已自动附）/ issue 反馈入口
- [x] **官网下载页核验**：确认站点「下载」页版本号 / 发布日期已随本次发版自动更新（`site.yml` 在 main push 后重建 `site-dist`，版本号不人工维护），并确认主下载与「Issues 留言获取备用链接」两条通道可达 — v26.10.0：首页与下载页均显示 26.10.0（2026-10-06 核验）；同批把下载页主通道改为**版本化直链**（`releases/download/v<版本>/…`，模板占位符随每版自动更新）
- [x] **归档发布验证记录**：复制骨架 → 新建 `docs/releases/<版本>-verification.md` 并填本次事实（tag / commit / workflow run / 资产哈希 / 真机项 / 发布后核验）——**清单是操作单、会被下一版重置；这份文件是不重写的历史** — v26.10.0：`releases/26.10.0-verification.md`（#275）

## 三、发布后 72 小时（RUNBOOK）

- [ ] 盯 GitHub Issues（无遥测，这是唯一反馈面）
- [ ] 盯 Release 下载量（Release 页侧栏 / API）
- [ ] 出问题：撤 latest 标记 → **发更高版本号的修复版** → README 置顶已知问题 → 公告说明

## 四、v1.x 待办（不阻塞本节点）

### 真机清单（下一发布节点并入）

- [ ] **桌面快捷方式生成确认**：`build.nsis.createDesktopShortcut` 已为 `true`（#218，配置层完成）——v26.10.0 真机未专项确认（用户装在自选目录）；并入下一节点真机冒烟。

### 长期

- [ ] winget 分发（`winget-create` 从 installer URL 生成 manifest，人工提 PR）
- [ ] 代码签名评估 —— **已决策：暂不采购（2026-10-02，#202）**；选项矩阵（Azure Trusted Signing 已排除：限美加 + 3 年实体）/ 触发条件 / 若触发的改造清单见 [`decisions/code-signing.md`](decisions/code-signing.md)
- [ ] 更多领域插件（`docs/domain-contract.md`；`jwb-domain-setup` 技能上线后引导用户自助生成）
