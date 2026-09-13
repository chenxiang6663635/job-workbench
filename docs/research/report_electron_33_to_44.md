# Electron 33 → 44 升级调研（为专门批次准备的清单）

> 来源与日期：官方 [Breaking Changes](https://www.electronjs.org/docs/latest/breaking-changes)（收录至 44）+
> 本仓库 `web/electron/main.js` 现状（2026-09-13 读回）。**这是调研，不是升级**——升级本身走独立批次。
> 触发原因：dependabot 提案 #67（electron 33.4.11 → 44.3.0 + electron-builder），CI 全绿但**CI 完全不碰 Electron**。

## 结论摘要

1. **我们的 Electron API 面很小**（下表），因此多数破坏性变更与我们无关；真正需要动手的只有 **打包链路（v42 起不再 postinstall 下载二进制）** 与 **平台底线（v44 停发 Windows 32 位、macOS 13+）**。
2. **`webContents` 的四个 API（`setZoomLevel` / `setVisualZoomLevelLimits` / `before-input-event` / `did-finish-load`）在 34–44 区间没有任何官方变更记录**——但它们正是本仓库刚交付的缩放功能，必须冒烟确认。
3. **不能靠 CI 验证这次升级**：现有四项检查（pytest / 前端构建 / 标题 / UI 冒烟）没有一项会启动 Electron。升级批次必须包含下面的实机冒烟清单。

## 一、我们实际用到的 Electron API（依据：`main.js` 行号）

| 模块 | 用法 | 位置 |
|---|---|---|
| `app` | `getPath("userData")`、`quit`、`isPackaged`、`whenReady`、`on(activate / before-quit / window-all-closed)` | `:32, :55, :153/186/249, :302, :368, :383-395` |
| `BrowserWindow` | 构造（`width/height/title/backgroundColor/webPreferences`）、`getAllWindows`、`setMenuBarVisibility(false)`、`loadURL`、`on("closed")` | `:253-267`、`:384`、`:265`、`:266`、`:270` |
| `webContents` | `setZoomLevel`、`on("did-finish-load")`、`setVisualZoomLevelLimits(1,1)`、`on("before-input-event")` | `:268-288` |
| `dialog` | `showMessageBox` ×2（自动更新的两次询问） | `:326`、`:345` |
| `electron-updater` | `autoDownload=false`、`on(error/update-available/update-not-available/update-downloaded)`、`downloadUpdate`、`checkForUpdates`、`quitAndInstall` | `:307-364` |
| Node 标准库 | `child_process`（spawn/execFileSync/taskkill）、`http`、`path`、`fs` | 全文件 |

**没有用到**（因此相应变更对我们无影响，逐条记下避免后人重复怀疑）：`clipboard`、`Notification`、`session.*`（含扩展与 cookie 监听）、`utilityProcess`、`setWindowOpenHandler`、`event.senderFrame`、`app.commandLine`、离屏渲染（OSR）、文件打开/保存对话框（`showOpenDialog`/`showSaveDialog`）、`console-message` 事件、`nativeImage`。仓库脚本里也**没有任何 `ELECTRON_*` 环境变量**引用。

**未显式设置、但必须对照默认值的键**：`webPreferences` 只写了 `contextIsolation: true` 与 `nodeIntegration: false`，`sandbox` / `webSecurity` 等一律走 Electron 默认值。**默认值变化不属于「调用了某个 API」**，恰恰是「API 面小所以没事」这种论证最容易漏掉的一类——升级时必须逐项对照 v44 的 `webPreferences` 默认值表，而不是只看本文的 API 清单。

## 二、34 → 44 逐版对照（只列与我们相关的）

| 版本 | 变更 | 对我们的影响 |
|---|---|---|
| 44 | **停发 Windows 32 位（win32-ia32）与 Linux ARM 32 位二进制** | 我们只出 win64（`build.artifactName` 固定 `-win64`、`win.target: nsis`），**无影响**；但要在升级批次里确认 electron-builder 没有顺带配置 ia32 |
| 44 | `clipboard` 不再暴露给渲染进程 + API 改 Promise | 我们不用 clipboard，**无影响** |
| 44 | `select-client-certificate` 事件扩展（`webContents` 可为 null） | 未订阅该事件，**无影响** |
| 44/38 | macOS 12 / 11 支持移除（v44 需 macOS 13+） | 只发 Windows，**无影响**（若将来出 macOS 包需注意） |
| 43 | `dialog` 的 `defaultPath` 默认改为 Downloads、系统不再记忆上次目录 | 我们只用 `showMessageBox`（无 `defaultPath`），**无影响** |
| 43 | `roundedCorners` 全平台默认 true（含 Linux） | Windows 上本就有圆角，视觉预期不变；升级后顺手看一眼窗口外观 |
| 42 | **不再通过 `postinstall` 下载 Electron 二进制**：改为首次运行按需下载，新增 `install-electron` 脚本，**`ELECTRON_SKIP_BINARY_DOWNLOAD` 失效** | ⚠️ **中风险**：我们的 `scripts/build_desktop.ps1` 依赖 `npm run dist`（electron-builder）。二进制获取现在走 `@electron/get`（构建期），理论上不受影响；但**首次 `npm install` + `npm start`（dev）与打包流程必须各实跑一次**，尤其是离线/带缓存的场景 |
| 42 | macOS 通知改用 UNNotification（需签名） | 未用 Notification，**无影响** |
| 41 | PDF 不再创建独立 guest WebContents（改在同一 WebContents 内渲染） | ⚠️ **低-中风险**：素材库页用 `<iframe>` 预览 PDF（`Library.tsx` 的二进制分支）。渲染层行为变化需**实测 PDF 预览**仍然可滚动、不白屏 |
| 39 | `window.open` 弹窗始终可调整大小 | 不用弹窗，**无影响** |
| 38 | `plugin-crashed` 事件移除；macOS 12+ | 未监听该事件，**无影响** |
| 37 | Utility process 的未处理 rejection 行为变化 | 未用 utilityProcess，**无影响** |
| 36 | `app.commandLine` 会把开关转小写、不传给子进程 | 未用 `app.commandLine`，**无影响**；我们用 `child_process` 显式起后端，参数原样传递 |
| 35 | `console-message` 事件签名变化（`level` 变字符串） | 未监听，**无影响** |
| 34 | Windows 全屏时自动隐藏菜单栏 | 我们已 `setMenuBarVisibility(false)` 且不进全屏，**无影响** |
| 33（范围外，但升级时一起确认） | frame 相关 API 可能返回 `null`/detached；原生模块需 C++20 | 我们无原生模块、不碰 frame API；`main.js` 只用 Node 标准库，**无影响** |

**跨多代的隐性升级**：33 → 44 同时跨越 11 代 Chromium 与多代 Node。我们的主进程只依赖 Node 标准库（`fs`/`path`/`http`/`child_process`），所以语言/运行时层面的风险低；**但渲染进程（React 应用）跑在新 Chromium 上，需按 UI 冒烟 + 人工点页确认**。

## 三、风险分级与对应验证

| 级别 | 事项 | 验证方式 |
|---|---|---|
| 中 | 打包链路（v42 postinstall 变更）与 electron-builder 取二进制 | 完整跑 `scripts/build_desktop.ps1` 出安装包 |
| 中 | 缩放四件套（`setZoomLevel` 等）无官方变更记录 ≠ 无行为变化 | dev 启动实测 Ctrl+= / Ctrl+- / Ctrl+0、重启后级别沿用 |
| 中 | 自动更新链路（electron-updater ^6.8.9 对 Electron 44） | 看 `main.log` 的 `checkForUpdates` 结果；能走通「已是最新」分支即可，真正的下载/安装需新版本存在 |
| 低-中 | PDF 预览（v41 OOPIF） | 素材库页打开一份 PDF，确认可滚动、无白屏 |
| 低-中 | **渲染进程跨 11 代 Chromium**（CSS 行为、`Intl`/日期、被移除的 Web API） | `npm run test:ui` 只覆盖布局与 a11y 最小集——需**人工遍历七个页面功能**（图表渲染、表单交互、简历 A4 预览、岗位抓取与解析） |
| 低 | 窗口外观（v43 圆角） | 目测 |
| 低 | 打包资源缓存（NSIS / winCodeSign 版本可能随 electron-builder 变化而刷新） | 打包时观察是否卡下载；卡住按脚本备注用自带 7za 手动解压到对应缓存目录 |
| 低 | 后端进程收尾（`taskkill /t` 路径） | 关窗后 `tasklist` 查无 uvicorn/python 残留 |

## 四、桌面冒烟清单（升级批次逐条执行并记录结果）

1. **dev 启动**：`cd web/electron && npm install && npm start`
   - 窗口出现、标题 `Job Workbench`；`main.log`（`%APPDATA%/job-workbench/main.log`）无红色异常。
   - 缩放：`Ctrl + =` / `Ctrl + -` 各三次（到上下限不越界）、`Ctrl + 0` 复位；重启后级别沿用（读 `zoom.json`）。
   - 语言切换后窗口标题跟随（切到中文应为「求职工作台」）。
   - 关窗后：`tasklist | findstr /i "python uvicorn"` 无残留进程。
2. **打包**：`powershell -ExecutionPolicy Bypass -File scripts\build_desktop.ps1`
   - 产物：`web/electron/release/job-workbench-setup-<版本>-win64.exe` + `.blockmap` + `latest.yml`。
   - 若卡在 winCodeSign 下载，按脚本提示用自带 7za 手动解压（既有备注）。
3. **安装与运行**：`Setup.exe /S /D=<临时目录>` → 启动 → `http://127.0.0.1:8765` 可访问 → 七个页面各点一次（数据用 demo 工作区）。
4. **自动更新路径**：已装旧版（v0.2.1+）启动 → 等 5 秒检查 → 确认 `main.log` 有结果、弹窗交互仍是「先问下载、再问重启」；若恰好有新版本可完整走一遍下载/安装。
5. **PDF 预览与 A4 预览**：素材库页 PDF、简历工坊 A4 预览；简历导出的 PDF 在系统阅读器里正常打开。
6. **异常路径**：未启动后端时的界面提示（`online=false` 分支）、端口占用时的复用提示、`JOBWS_NO_BROWSER=1` 不弹浏览器。
7. **回归**：升级完成后在 main 上跑一次 `npm run test:ui`（UI 冒烟，确认新 Chromium 下布局/a11y 仍绿）；`python -m pytest tests/ -q`。

## 五、建议的执行顺序

1. 先在分支上把 `web/electron/package.json` 的 `electron` 提到 v44（`electron-builder` 同步），**不要**同时改其他依赖。
2. 按第四节 1–7 逐条做，结果记进 PR（这是本批唯一能证明升级没坏的凭据）。
3. 若第 1 条冒烟即失败：查 v44 的 release notes 与 `electron-builder` 对 v44 的支持声明；必要时退到「当前 Electron 能被支持的最高 LTS 线」，把大跨度升级拆成两段（例如 33 → 38 → 44）。
4. 合并后打 patch 版本（`fix(electron): …`）走一次 release 流程，验证安装包与自动更新元数据。
5. 说明：**Electron 33 已 EOL（无安全更新）**，这次升级不应无限期推迟；但要按上面的实测路径走，不接受「CI 绿了就算完」。

## 六、未核实项（如实标注）

- v44 对应的 Node/Chromium 具体版本号（官方 Breaking Changes 页不列）——需要时查 Electron Releases。
- `electron-builder ^25.1.8` 是否声明支持 Electron 44（本机无法在不安装的情况下核实；打包那一步会给出答案）。
- 自动更新的**真实**下载/安装路径（需要存在一个更高版本才能走完；本次最多验证「检查 + 已是最新」分支）。
