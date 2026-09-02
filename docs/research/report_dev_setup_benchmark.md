# 调研报告：本地优先桌面应用的开发设置基准

- 日期：2026-09-01
- 触发：用户在执行 PyInstaller 打包前，要求借鉴 GitHub 相似项目的开发设置，找亮点与空白。
- 查询类型：Breadth-first（三路 subagent 并行：打包分发 / 数据目录 / 工程设置）
- 与既有调研区别：`report_job_search_products.md` 是**产品功能层**；本报告是**工程配置层**。
- 公众号中文源：搜狗接口历史 SSL 故障，本轮未再尝试；三路英文源已覆盖核心议题。

## 执行摘要

三路调研得出两条会直接改写我们打包方案的结论：**①PyInstaller 应走 onedir 而非 onefile**（业界最成熟的 VOICEVOX 即如此，规避 `sys._MEIPASS` 与杀软误报）；**②"数据放 exe 旁"是特例而非主流**，装在 Program Files 会写入失败，需加"可写性探测 + 回退系统用户目录"的优先级链。此外工程设置上我们有大量空白（无 CI/无日志/无锁文件/无测试），但多数不是单人维护的必需品。

---

## 一、打包与分发（A 路）

### 案例对比

| 项目 | 打包方式 | 免环境 | 启动/退出 | 对我们的借鉴 |
|---|---|---|---|---|
| **VOICEVOX**（业界最成熟） | PyInstaller **onedir**（`exclude_binaries=True` + `COLLECT`），资源拷到 exe 同级 | 是 | localhost HTTP；发布校验脚本等引擎就绪**最多 150 秒** | 走 onedir；**必须有"等待后端就绪 + 超时提示"** |
| **FastClient**（12★，脚手架级） | PyInstaller `--onefile` | 是 | 无健康检查直接开窗（**缺陷**）；退出用 `taskkill /pid /f /t` | 学它的 **taskkill /t 杀进程树**；不学"开窗不等待" |
| **ComfyUI Desktop**（已归档） | 不用 PyInstaller，**捆绑 uv + 运行时建 venv** | 否（首次需联网装依赖） | node-pty 起 PowerShell 执行 uv | 若 PyInstaller 难收敛，这是 B 方案；我们依赖轻，PyInstaller 够用 |
| Fin-Agent Desktop（70★） | 构建脚本 + electron-builder | 待确认 | — | 参考价值有限 |

### 两个几乎必然遇到的坑

1. **uvicorn 动态导入必漏**：`uvicorn.logging`、`uvicorn.loops(.auto)`、`uvicorn.protocols.http(.auto/.h11_impl/.httptools_impl)`、`uvicorn.lifespan(.on/.off)` —— 必须显式写进 hidden imports。
2. **Windows 退出清不干净**：单靠 `process.kill()` 在 spawn 的 exe 上会留下 uvicorn 孙进程孤儿，必须用 `taskkill /pid X /f /t`（`/t` 杀子树）或 tree-kill。

### onefile 的代价（决定我们选 onedir）

- 启动慢（每次解压到临时目录）
- **杀软误报**（Windows Defender 报 Trojan:Win32/Wacatac；360/火绒同理），**UPX 压缩会显著加剧**
- onedir + 资源放 exe 同级可规避 `sys._MEIPASS` 路径坑

### 流程纪律

修好 `.spec` 后应始终 `pyinstaller --clean --noconfirm MyApp.spec` 重编，不要重新生成 spec 覆盖 `datas/hiddenimports`。

---

## 二、用户数据目录（B 路）— **影响我们决策**

### 策略对比

| 策略 | 典型应用 | 优点 | 缺点/隐患 | 适用 |
|---|---|---|---|---|
| **exe 同级（portable）** | VS Code Portable、Joplin `--profile` | U 盘携带、不留痕迹、路径直观 | **装在 Program Files 即不可写**；升级易被覆盖删除；无多用户隔离 | 免安装 zip 发行 |
| **系统用户目录（主流）** | AnythingLLM、Electron 默认 `userData`、Joplin 默认 | 一定可写、按用户隔离、卸载留存、符合 OS 规范 | 路径隐蔽、不便携 | **默认策略** |
| **用户自选（vault 模型）** | Obsidian、Logseq | 数据主权、可 git 同步、卸载不丢、最 local-first | 需实现切换与失效处理 | **内容型应用最贴合** |

### 对"数据放 exe 旁"的评价

**业界定位：特例而非主流。** VS Code 官方明确限定——Portable 模式**只支持 ZIP/TAR.GZ 免安装包，不要在用安装器安装的版本上配置**，且 Windows ZIP 版不支持自动更新。

**必须规避的坑**：Microsoft KNOWNFOLDERID 规范中 `%ProgramFiles%` 是机器级 FIXED 目录，不可写。若 exe 装在那里，`personal/` 写入直接 `PermissionError`。更糟的可能是被 UAC 虚拟化重定向到 `%LOCALAPPDATA%\VirtualStore\...`——数据"消失"到别处，升级后找不回来（该说法未取得微软一手验证，按最坏情况设计）。

### 建议的修法（加 fallback）

优先级链：
1. `--data-dir` 参数 / 环境变量 `MYAPP_DATA_DIR`
2. **exe 同级 `personal/`** —— 仅当该目录已存在或有 `portable.txt`，且 `os.access(path, W_OK)` 实测可写
3. 回退 `platformdirs.user_data_dir(...)`（Win `%APPDATA%`、mac `~/Library/Application Support`、Linux `~/.config`）

**关键区分**：`dist` 是**只读资产**，留 exe 旁完全没问题；**只有 `personal/` 需要可写目录**。
启动时做写入探测，**失败要给明确 UI 错误 + 引导迁移，不要静默降级**。

### 跨平台路径获取

- Python 3.8 无内置等价物，需 pip 装 `platformdirs`（`appdirs` 已停维护）
- Electron：`app.getPath('userData')` + `app.setAppLogsPath()`
- 迁移/升级：数据根放 `schema_version` 标记，启动时比较并按序执行迁移，迁移前自动备份

---

## 三、工程设置（C 路）— **我们的空白**

### 现状 vs 成熟项目

我们现状：有 `eslint.config.js`、`package-lock.json`、`electron-builder`（只配 `win.nsis`）、`backend/requirements.txt`（仅上界约束）。
**完全没有**：`.github/`、pre-commit、Prettier、任何测试、Python 锁文件、日志。

| 设置项 | 成熟项目做法 | 我们 | 必要性（单人维护视角） |
|---|---|---|---|
| CI（lint+tsc+单测） | GitHub Actions | ❌ | **必做**（本机 Windows 之外的验证） |
| 跨平台构建 | matrix 三平台 | ❌ | 推荐（见下） |
| 依赖锁定 JS | 提交 lock + CI 用 `npm ci` | 部分 | **必做** |
| 依赖锁定 Python | `uv.lock` 提交 | ❌ | **必做/推荐** |
| 版本号统一 + CHANGELOG | semver | ❌（三端各写各的） | **推荐** |
| 日志文件 | winston / logging 落盘用户目录 | ❌ | **必做**（本地应用唯一排障手段） |
| 单测 | vitest（后端+纯函数） | ❌ | 推荐 |
| 打包冒烟测试 | `--dir` 后起进程校验 | ❌ | **推荐**（成本低收益高） |
| Prettier | eslint + prettier | 部分（仅 eslint） | **必做** |
| pre-commit | husky/pre-commit | ❌ | 可选（单人可省） |
| 自动更新 | electron-updater（2 行代码） | ❌ | 可选（分发时才需） |
| 代码签名 | macOS 必须 mac 上做；Windows EV 证书 | ❌ | 可选（分发时才需） |
| Playwright E2E / Sentry / changesets | 大项目才有 | ❌ | **过度，不做** |

### 单人维护优先级

- **P0（先做）**：①三端统一版本号 ②Prettier ③一条 CI（Windows runner 即可）④Python `uv.lock` ⑤日志文件
- **P1（分发时做）**：⑥release 自动发布 draft ⑦打包冒烟脚本
- **P2（可选）**：⑧electron-updater ⑨pytest + 少量 vitest ⑩pre-commit
- **明确不做**：Playwright E2E、Sentry、changesets、多 workflow 拆分、变更门禁

### 跨平台构建可行性（对 Windows 单人开发者）

- electron-builder 官方："Don't expect that you can build an app for all platforms on one platform"
- **macOS 代码签名只能在 macOS 上做，无法绕过**；但 GitHub Actions `macos-latest` 能出**未签名**包（用户需手动放行 Gatekeeper）
- Windows 目标可用 Linux + Wine 交叉编译；**建议先只维护 Windows 包，不做本地交叉编译**

---

## 四、对我们 a+b 计划的影响（关键）

| 原计划 | 调研发现 | 建议调整 |
|---|---|---|
| PyInstaller `.spec` 打包（未定 onefile/onedir） | onefile 有解压开销+杀软误报；VOICEVOX 走 onedir | **改为 onedir**，资源放 exe 同级 |
| `personal/` 与 `dist` 都放 exe 旁 | 装在 Program Files 会写入失败 | **加可写性探测 + 回退系统用户目录**（dist 只读可留 exe 旁） |
| hidden imports 待定 | uvicorn 动态导入必漏 | 显式加 uvicorn hidden imports |
| Electron 退出 kill 后端 | `process.kill()` 留孤儿进程 | 改用 `taskkill /f /t` 杀进程树 |
| 无等待就绪超时 | VOICEVOX 等 150 秒；FastClient 不等待是缺陷 | 保留我们的轮询等待（已实现），加超时提示 |

## 五、局限性

- 公众号中文源未纳入（搜狗 SSL 故障遗留），可能遗漏国内开发者对杀软误报、便携版的一手经验。
- onefile 杀软误报、UAC 虚拟化重定向两条来自中文技术博客/社区经验，非官方结论，按"最坏情况"设计。
- FastClient 仅 12★/3 commits，属脚手架级，其做法仅作流程参考，未经真实用户验证。

## References

1. [VOICEVOX/voicevox_engine run.spec (raw)](https://raw.githubusercontent.com/VOICEVOX/voicevox_engine/master/run.spec)
2. [Build and Packaging | VOICEVOX/voicevox_engine | DeepWiki](https://deepwiki.com/VOICEVOX/voicevox_engine/6.1-build-and-packaging)
3. [GitHub - fastapiadmin/FastClient](https://github.com/fastapiadmin/FastClient)
4. [FastClient frontend/electron/main.js (raw)](https://raw.githubusercontent.com/fastapiadmin/FastClient/master/frontend/electron/main.js)
5. [Python Environment Management | Comfy-Org/desktop | DeepWiki](https://deepwiki.com/Comfy-Org/desktop/2.3-python-environment-management)
6. [Coze2JianYing/build.py（hidden-import 列表）](https://github.com/Gardene-el/Coze2JianYing/blob/main/build.py)
7. [PyInstaller Hooks 官方文档](https://pyinstaller.org/en/stable/hooks.html)
8. [Electron app 模块文档（getPath/setAppLogsPath）](https://www.electronjs.org/docs/latest/api/app#appgetpathname)
9. [VS Code Portable mode 官方文档](https://code.visualstudio.com/docs/setup/portable)
10. [AnythingLLM Desktop — Where is my data stored?](https://docs.anythingllm.com/installation-desktop/storage)
11. [Microsoft Learn — KNOWNFOLDERID](https://learn.microsoft.com/en-us/windows/win32/shell/knownfolderid)
12. [platformdirs API 文档](https://platformdirs.readthedocs.io/en/latest/api.html)
13. [electron-builder – Multi Platform Build](https://www.electron.build/docs/features/multi-platform-build)
14. [electron-builder – Auto Update](https://www.electron.build/docs/features/auto-update)
15. [Electron – Code Signing](https://www.electronjs.org/docs/latest/tutorial/code-signing)
16. [CherryStudio .github/workflows/ci.yml](https://raw.githubusercontent.com/CherryHQ/cherry-studio/main/.github/workflows/ci.yml)
17. [uv – Locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
