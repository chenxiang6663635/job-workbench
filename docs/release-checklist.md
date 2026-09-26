# 发布检查清单（Release Checklist）

> 每次打 tag 前过一遍。分两栏：**CI 自动**（release.yml 已固化，绿了就是过了）与
> **人工必做**（必须有人的判断或桌面会话，机器替代不了）。配套阅读：CONTRIBUTING
> 的「发布流程」六步与「版本号体系」；版本号 = 月粒度 CalVer `YY.MM.N`（`26.9.0`
> 首发 / `26.9.1` hotfix / `26.10.0` 换月）。
>
> 出事了怎么办（RUNBOOK，见第三节）：**撤 latest 标记 → 发一个版本号更高的修复版**
> ——electron-updater 不会接受相同或更低的版本号覆盖，「删掉坏的 Release 重传」无效。
>
> **本轮（v26.9.0）的勾选状态：2026-09-26 记录**。CI 那七项与「版本落章」三项已由
> 演练 `36205442739` 与 `release check --tag v26.9.0`（exit 0）验证并勾选；真机与发布
> 那几项留空等人工。下一个发布节点请把勾选重置（清单是可复用的操作单，不是台账）。

## 〇、发布阻断清单（任一存在即不发布）

数据损坏 / 静默覆盖 · secret 泄漏 · 路径越界 · installer 装不上或起不来 · 更新链失效 · 主流程阻断 · privacy 文案与行为不一致 · backup–restore 不可靠。其中四类**不等功能批次**、可直接 `26.9.N` hotfix：安全 / 数据损坏 / 安装·启动阻断 / 更新链失效。完整定义与发布窗口纪律见 CONTRIBUTING「发布治理」。

## 一、CI 自动（release.yml，绿了即过）

- [x] 闸 1：tag `v26.9.x` 与 `web/electron/package.json` 的 version **逐字一致** — v26.9.0：演练 `36205442739` 通过（package.json 读为 `26.9.0`）
- [x] 闸 2：CHANGELOG 有同名版本段（抽段即 Release 说明） — v26.9.0：`release check --tag v26.9.0` exit 0，段存在
- [x] 闸 3：产物 exe + `latest.yml` 真实产出（缺 latest.yml 拒发——老用户收不到更新） — v26.9.0：exe 122 MB 级 + `latest.yml`（26.9.0 + sha512 + size）已在演练 artifact 内核过
- [x] 后端 exe 冒烟（`scripts/smoke_backend_exe.py`：起产物 → 健康检查） — v26.9.0：演练内步骤通过（起进程 + `/api/system/check` + 资源自检）
- [x] **安装/卸载冒烟**（NSIS `/S` 静默装 → 验证 → 静默卸载；2026-09-24 新增） — v26.9.0：演练内装→验→卸→等目录消失全通过
- [x] **SHA256SUMS.txt** 生成并挂 Release（**完整性**补偿：证明下载未损坏、与已发布文件一致；**不构成发布者身份认证**——未签名场景的身份信任根是 GitHub 账号与仓库保护） — v26.9.0：清单已生成，本地重算 exe 哈希与清单一致
- [x] **Release notes 自动附加**未签名 / SmartScreen 说明（微软官方口径：未签名拦截页更严重、每版本信誉归零） — v26.9.0：`release-notes.md` 尾部含中英安装说明 + 校验和块
- [ ] 发布后核验资产：exe + blockmap + latest.yml + SHA256SUMS.txt 四样全在（**打 tag 后**才做）

## 二、人工必做（发布日，约 15 分钟 + 真机）

**版本落章**：

- [x] `python tools/jobws.py release version` 取号 → bump `web/electron/package.json`（同一号） — v26.9.0：#189 已落章（package.json / plugin.json / 技能 metadata 三处同步）
- [x] CHANGELOG `[Unreleased]` 改为 `[版本号] - ISO 日期` → `release check --tag v<号>` 绿 — v26.9.0：`## [26.9.0] - 2026-09-25`；`release check` exit 0
- [x] dry_run 演练：`gh workflow run release.yml -f dry_run=true -f tag=v<号>` → 下载 artifact 里的安装包 — v26.9.0：四轮演练，最新 `36205442739` success（并行结构首跑），产物已下载核验

**真机冒烟**（自己的 Windows 真机，CI 没有桌面会话）：

- [ ] **通知实测**：造一条今天到期的待办 → 确认 toast 真的弹出（CI 测不了通知；AUMID 2026-09-24 修复后的首次实测必须做）
- [ ] **双开**：第二个实例应直接退出并聚焦已有窗口
- [ ] **离线启动**：断网启动应安静（更新检查失败只进日志，不弹窗）
- [ ] 人眼验收四项：八个页面各操作一遍 / 深浅主题各看一遍 / 设置页搜索与单项还原 / 中英切换

**发布**：

- [ ] `git tag -a v<号> -m "..." && git push origin v<号>` → CI 走完
- [ ] `gh release view` 核资产四样 → **真下载一次** → 核对 SHA256
- [ ] **发布后完整验证链**（人工至少一次——验的是"用户拿到的东西"，不是本地构建产物）：真下载 → 安装 → 首次启动 → 建工作区 → 打开旧工作区 → 退出 → 再启动 → 卸载（CI 已自动覆盖安装/卸载冒烟；这条是人眼版）
- [ ] 发布公告要素：定位一句话 / 隐私承诺（**按 `docs/data-flow-matrix.md` 表述**——不复述"不联网"类绝对句）/ SmartScreen 说明（已自动附）/ issue 反馈入口

## 三、发布后 72 小时（RUNBOOK）

- [ ] 盯 GitHub Issues（无遥测，这是唯一反馈面）
- [ ] 盯 Release 下载量（Release 页侧栏 / API）
- [ ] 出问题：撤 latest 标记 → **发更高版本号的修复版** → README 置顶已知问题 → 公告说明

## 四、v1.x 待办（不阻塞本节点）

- [ ] winget 分发（`winget-create` 从 installer URL 生成 manifest，人工提 PR）
- [ ] 代码签名评估（Azure Artifact Signing ≈$9.99/月限地区 / OV 证书 $150–300/年；触发条件：SmartScreen 误报成为高频 issue）
- [ ] 更多领域插件（`docs/domain-contract.md`；`jwb-domain-setup` 技能上线后引导用户自助生成）
