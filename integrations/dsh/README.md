# job-workbench × DeepSeek Harness（DSH）

把求职工作台接进 DSH 宿主：**MCP 工具面**（15 个工具，两段式写入）+ **9 个 `jwb-*` 技能** +
可选 **`jobws` agent preset**。本目录同时是 npm 包 **`dsh-job-workbench`** 的源码
（`package.json` 的 `dsh.bundle.patch` 指向 `cordis.patch.yml`）——**装包即接线，不需要手改任何
profile 文件**（与第一阶段「把 insert 块抄进 profile」的本质区别）。

三条 insert 一张表（细节与理由见 `cordis.patch.yml` 头注）：

| 行 id | 干什么 | 依赖 |
|---|---|---|
| `mcp-jobws` | MCP 工具面（stdio → `jobws-mcp`） | 平台预构建 `jobws-mcp.exe`（P2-2 产出）；开发态可用覆盖层指到本机 venv |
| `preset-jobws` | 可选 agent preset（求职语境 + 工具集基线） | `@deepseek-ai/dsh-agent-preset` |
| `skill-filesystem-jobws` | 独立技能 provider，只挂**本包** `skills/` 镜像 | `@deepseek-ai/dsh-skill-filesystem` |

**数据根刻意不写进配置**（数据根 spec 决策 1）：`jobws-mcp` 自己读工作台的持久化选择与 B3 默认；
`config.env.JOBWS_DATA_DIR` 只作应急覆盖——写死它会制造第二个事实源。

## 一、用户态（推荐）：装包

```powershell
# 发布后：
dsh plugin --profile <你的 profile> add dsh-job-workbench
# 开发期 / 离线 / 尚未发布时（link 直挂本仓库）：
dsh plugin --profile <你的 profile> add link:<仓库路径>\integrations\dsh
```

- `dsh plugin add` 会**自动写两处**：profile 的 `dependencies` 与 `dsh.profile.bundles`；
  再重启 DSH（替换已装包要走重启才会装载新的清单与模块）。
- 装完在会话里应能看到 `mcp__jobws__*` 工具；技能清单里出现 9 个 `jwb-*`（来源为本包）。
- **从第一阶段手工接线迁移过来的人**：先删掉 profile `cordis.patch.yml` 里手抄的
  `mcp-jobws` / `preset-jobws` insert 条目，再装本包——**否则双挂载**（同一 `serverName`
  注册两次）。

## 二、开发态：link 直挂 + 本机 venv

```powershell
# 1) 生成随包技能镜像（唯一真源 = 仓库 skills/；防漂移由 four-ends 检查兜底）
python tools\jobws.py skills install --target dsh
#    或一条龙（含校验；-Pack 预演 npm pack 的内容清单）：
#    powershell -ExecutionPolicy Bypass -File scripts\build_dsh_bundle.ps1 -Pack

# 2) 装包（link 形态；改完源码重启 DSH 即生效）
dsh plugin --profile <你的 profile> add link:<仓库路径>\integrations\dsh

# 3) exe 未就位时，用覆盖层把命令指到本机 venv（一次性叠加，不改任何 profile）
dsh headless --patch <本目录>\cordis.patch.yml --patch <本目录>\dev-python-overlay.yml "你好"
# 已装包后也可临时叠加：dsh --profile <你的 profile> --patch <本目录>\dev-python-overlay.yml
```

`cordis.patch.yml` 里的路径全部用 `!!js` + `baseUrl` 现算（官方 agent-preset 同款：
`createRequire(baseUrl).resolve('dsh-job-workbench/package.json')` 从 **profile 目录**解析本包，
因此 `package.json` 必须保留 `"exports": { "./package.json": ... }`）——**link 直挂与 npm 安装
两种形态成立，零绝对路径**；注意基点：只有「装过包（link 或正式包）」的 profile 里本包才可解析，
**只 `--patch` 叠加而不装包**时技能行会报 `Cannot find module 'dsh-job-workbench/package.json'`
（预期行为——先装包，或忽略该行只用 MCP 部分）。

## 三、升级 / 卸载 / 回滚

```powershell
# 升级（发布后）：装新版本号即可；link 形态改回 git 旧提交即回滚
dsh plugin --profile <p> add dsh-job-workbench@<新版本>
# 卸载：CLI 会把 dependencies 与 dsh.profile.bundles 两处一并清理（2026-10-07 实测）
dsh plugin --profile <p> remove dsh-job-workbench
```

- **数据零影响**：本包只加「读取与调用入口」，不迁移、不写工作区；卸载不动数据。
- 回滚演练（首次接线前）：`Get-FileHash <profile>\package.json, <profile>\cordis.patch.yml`
  留基线；改后核对哈希只在预期文件上变化。

## 四、验收清单（每个接触 DSH 的改动跑一遍）

1. **合成**：`dsh --profile <p> --patch <本目录>\cordis.patch.yml --dump-config` → 三条
   `jobws` 行（`mcp-jobws` / `preset-jobws` / `skill-filesystem-jobws`）都在；无
   `entry ... not found` 警告。（`--dump-config` 只做合成、**不求值** `!!js`。）
2. **激活**：会话里调含 `jobws` 的工具，打印 `dataRoot.state` → 与
   `python tools/jobws.py doctor` 一致。
3. **spawn 计数**：stdio 协商会**先后起两个进程**（临时探针 + 服务）——健康检查 / 重复
   进程检测必须把探针算进去，否则会误报「启动了两个 server」。
4. **两段式**（有写入的会话）：`preview_*` 之后**没有**落盘；出示 diff 并经用户确认后
   `apply_approval` 才写入（可对临时工作区演练）。
5. **preset**：桌面会话里切到 `jobws` 开始新会话；`dsh headless` 下 `preset-jobws` 停
   pending 属已知边界（见下）。
6. **技能**：技能清单出现 9 个 `jwb-*`，来源 = 本包 `skills/`。（仓库内开发时项目级
   `.agents/skills` 也在发现根里，同名技能会有两个来源候选——按宿主 rank 取先者，不重复挂载。）

## 五、已知边界（写清楚比含糊兜住更有用）

- **工具名会被宿主规范化**：`jobws.info` → `mcp__jobws__jobws_info_<12位哈希>`（点转下划线
  并加哈希后缀）。提示词 / 技能里**不要硬编码**宿主侧完整名——说「含 `jobws` 的工具」或
  按功能描述即可。
- **DSH 不支持 MCP 提示模板**（已实证）：四个工作流（JD 评估 / 投递包 / 面试复盘 / 今日待办）
  由 `jwb-*` 技能与 `jobws` preset 承载；`mcp/prompts.py` 保留给支持提示模板的宿主。
- **headless 一次性 profile 无 `agentPresets` 服务**（2026-10-06 真机实证）：`dsh headless`
  下 `preset-jobws` 停在 pending（信息级优雅降级，非缺陷）——persona 前缀在 headless 会话里
  不生效；两段式纪律由 MCP 工具描述自描述生效。**preset 的生效面 = 桌面会话 / 设置里切换**。
- **MCP 看不到源码形态的应用根**（结构性盲区）：工具报「无歧义」不等于全机无歧义——
  详见 `docs/mcp-integration.md` §三。
- **Windows first**：随包运行时目前只构建 `win32-x64`（`platform/win32-x64/`）；其他平台
  命令解析会回落到包内该路径并在启动期安静失败（`failOnStartupError: false`）——技能与
  固定件不受影响，MCP 工具面待平台子包补齐。
- **旧文件去哪了**：第一阶段的 `profile.patch.yml` / `preset.yml` 已收敛为
  `cordis.patch.yml`（内容等价，另加技能 provider 与 `!!js` 路径现算）。
