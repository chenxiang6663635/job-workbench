# 求职工作台 · 使用手册

English（主版）：[`usage-guide.md`](usage-guide.md) ｜ 本文件是简体中文同步版，内容与主版一致。

从零开始把工作台跑起来，以及日常使用的完整说明。

遇到问题先看最后的「常见问题」，覆盖了黑屏、端口占用等已踩过的坑。

---

## 一、一次性环境准备

只需做一次。已配好可跳过。

### 必装

| 软件 | 用途 | 检查命令 |
|---|---|---|
| Python 3.12+ | 后端与 CLI 脚本（3.12 是支持与 CI 验证的基线；3.9+ 或可运行但未验证） | `python --version` |
| Node.js 18+ | 前端构建 | `node --version` |
| Chrome 或 Edge | PDF 生成（headless 渲染） | 一般自带 |

### 安装依赖（各一次）

```bash
# 后端依赖（上限已随 3.12 基线逐步放宽、每条跑全量回归后才合；当前值见 CONTRIBUTING.md）
cd <仓库目录>\web\backend
pip install -r requirements.txt

# 前端依赖
cd <仓库目录>\web\frontend
npm install
```

### 初始化你的工作区（已有 personal/ 的跳过）

```bash
python tools/jobws.py init --target personal --domain hvac-cooling
```

只想先看看界面长什么样、不想先填任何真实信息的话，用 `--demo`：

```bash
python tools/jobws.py init --target demo --demo
```

它会额外铺一份占位数据（8 条投递 / 3 场面试 / 2 位联系人 / 1 个 Offer /
3 场宣讲会 / 6 道题 / 2 张解析卡 / 1 份简历），公司与人名全是假的，可以直接上手体验或截图；
同时会默认装入 software-backend 插件（demo 数据的方向字段依赖它）。
启动后在右上角工作区下拉里选 `demo` 即可。

---

## 二、日常启动：Web 界面

### 方式一：一键启动（推荐）

```powershell
cd <仓库目录>\web
.\start.ps1
```

脚本会自动：清掉被占用的端口 → 启动后端（8765）→ 启动前端（5173）→ 等待就绪 → 自动打开浏览器。

**关闭方式**：关掉脚本所在的控制台窗口，两个服务一起停。

### 方式二：手动启动（需要看后端日志时用）

开两个终端：

```bash
# 终端一：后端
cd <仓库目录>\web\backend
python -m uvicorn main:app --port 8765

# 终端二：前端（Windows 必须用 npm.cmd，直接跑 npm 会静默失败）
cd <仓库目录>\web\frontend
npm.cmd run dev
```

### 访问地址

| 地址 | 是什么 |
|---|---|
| http://localhost:5173 | **工作台界面（日常用这个）** |
| http://localhost:8765/docs | 后端 API 交互文档（FastAPI 自动生成） |

> 前端把 `/api` 请求代理到 8765，所以浏览器只跟 5173 打交道。

### 方式三：双击 exe（免环境，适合给别人用 / 快速查看）

构建产物在 `web/backend/dist/job-workbench-backend/`，双击其中的 `job-workbench-backend.exe`：

- **没服务在跑** → 启动后端 + 自动打开浏览器（黑色控制台窗口是服务日志，关掉=停服务）
- **服务已在跑** → 直接打开浏览器，不会重复起服务
- **端口被其他程序占用** → 人话提示，窗口保持打开（不会闪退）

> ⚠️ **exe 是"干净分发物"，不读你的个人数据**。便携版的工作区在 exe 旁边（`personal/`，默认为空）——这是刻意设计，避免你的求职数据随安装包散播。**自己日常用方式一/二（数据在仓库根）**；exe 用来验证产品或发给别人。硬要 exe 读自己的数据，设环境变量 `JOBWS_DATA_DIR` 指向仓库根（不推荐，容易数据分叉）。

重新构建 exe：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_backend_exe.ps1
```

### 桌面安装包（Electron 壳，v0.1.1 起）

不想配环境可以用 [Release](https://github.com/chenxiang6663635/job-workbench/releases/latest) 里的 `job-workbench-setup-*.exe`（Electron 窗口 + 打包好的后端，双击装完即用）。数据目录：安装版在 `%APPDATA%\job-workbench\personal\`，绿色版（backend exe 旁有 `portable.txt`）在 exe 旁 `personal\`——**卸载安装版不影响 %APPDATA% 里的数据**。

安装包现在是**向导式**：可以自选安装位置，并选择「为所有用户 / 仅为我」。**升级旧版时请沿默认选项**（「仅为我」+ 原目录）——选「所有用户」会装到 `Program Files` 并与旧安装分叉。静默安装仍可用：`/S`（`/D=<目录>` 可指定位置）。

桌面版可以调界面缩放：**设置页的「界面大小」滑块**（拖动即预览，整个界面含文字一起缩放），或 `Ctrl + =` 放大、`Ctrl + -` 缩小（0.5 级步进，约 0.58x–1.73x）、`Ctrl + 0` 复位；级别会记住，重启沿用，滑块与快捷键互相同步。

一键重建安装包（前端 dist → PyInstaller 后端 exe → NSIS）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_desktop.ps1
```

产物在 `web/electron/release/job-workbench-setup-<版本>-win64.exe`（产品名英文化为 **Job Workbench**：安装包与开始菜单项是英文；窗口标题跟随界面语言）。冒烟：`<安装包> /S` 静默安装到默认的「仅为我」位置（`/D=<目录>` 可指定位置），启动后验证 `http://127.0.0.1:8765`。

---

## 三、Web 界面八个页面

### 看板（首页）

打开就是它。回答三个问题：投了几家、几家还在流程中、接下来七天该干什么。

- 顶部四张统计卡：投递总数 / 流程中 / 近七天待办 / 已过截止（点击可下钻到追踪表）
- 投递漏斗：每个阶段多少人（待投→已投→笔试→…→签约），点柱子按阶段下钻
- **待推进**：健康度异常（紧急/逾期/停滞）的活跃岗位清单，每条带具体理由，点击下钻
- 近七天待办：下次动作日期或截止日期落在未来 7 天的记录（可一键顺延 7 天）
- **近 7 天宣讲会**：宣讲会 / 招聘会里时间落在未来 7 天的活动（点条目直达「准备」页的宣讲会页签）
- 已过截止提醒：还停在「待投」但截止日期已过的记录（红色）
- 静默提醒：长期无进展的活跃岗位（默认超 14 天）
- **周期复盘**：阶段转化率（从时间线重建）、停留中位天数、失败归因与**失败原因聚类**

### 追踪表

所有投递记录的表格。六件事：

- **筛选与搜索**：按阶段 / 方向 / 批次过滤，关键字搜公司、岗位或备注
- **排序**：下次动作日期 / 评分 / 停留天数 / **健康度**（紧急 > 逾期 > 停滞 > 正常，徽章悬停显示理由）
- **改状态**：点某行的「当前阶段」下拉框直接改（待投→已投→笔试…），改完自动保存
- **新增与批量导入**：右上「新增投递」逐条录入；「批量导入」粘贴或上传 CSV，先出差异预览（新增/重复/错误分色，带行号与原因），有错误行时禁提交
- **状态原因**：每行就地编辑；**进入「已挂 / 已放弃」必须填原因**，且这两态一旦进入就不可再改阶段（想重新投要新建一条）
- **行展开**：查看该记录的变更时间线与当前阶段停留天数

**两条约束（CLI 与网页同源，自动拦）：**
1. **终态不回退**：已挂 / 已放弃后「当前阶段」锁定，只可补状态原因与备注
2. **同公司+岗位去重**：重复录入会被拦截并提示既有记录 id（挂了之后再投一次则放行）

> 方向下拉框的选项来自工作区装入的领域插件（`config/directions/`），不是写死的。

### 岗位池

管理你看过的岗位。每张卡片显示公司_岗位、评分、档位。

- **新建岗位**：粘贴完整 JD 原文（职责+任职要求）系统原样存档；或粘贴**网页链接自动抓取正文**（需登录 / 反爬 / 纯 JS 渲染的页面会明确提示手动粘贴，不假装成功）
- **点开详情**：左边 JD 原文，右边解析卡
- **资格硬门槛（置顶优先）**：解析卡顶部的「资格硬门槛」卡片先于分数展示——通过（绿）/ 不通过（红）/ 待确认（琥珀）三态。**不通过时明确标红置顶**，这时分数是次要信息（说明资格不够，别投）
- **评分下钻**：四维（技术/经历/方向/培养）每条可点开，展开逐条命中明细——每条带能力分层（Primary/Secondary/Weak）+ **证据标签**（精确/模糊/语义徽章）+ 命中说明。想知道"为什么得这个分"点开看
- **简历差距面板**：该 JD 与你简历的差距清单，区分「可召回」（母版里有）与「真实缺口」（只能补经历）
- **解析卡**：评分由 AI 在 CodeBuddy 里完成后写入 `解析卡.md`，这里自动显示四维度进度条 + 总分 + 档位
- 还没评分的岗位显示"尚未生成解析卡"及操作指引——**网页不做评分**，评分是 AI 的工作

### 简历工坊

**双模式**：

- **标准版式**（数据驱动）：左结构化表单、右 A4 实时预览；页面直接新建版本；生成 PDF 后回显 ATS 校验与纸型检查；含防超页护栏
  - **版式与强调色**：版式下拉内置经典 / 紧凑 / 强调三套（全部单栏、过 ATS 校验；紧凑适合内容多、要压一页）；强调色四档（石墨灰 / 商务蓝 / 深墨绿 / 酒红）与版式自由组合，切换即刷新预览，生成的 PDF 与预览同源。命令行等价物：`resume render --template std_compact --resume-accent 酒红`
  - **一键导入**：上传 PDF / Word(.docx) / Markdown / 纯文本 → 抽取成结构化字段。**抽取而非生成**：模型未抽到的字段标黄、疑似补全的标红，核对页逐段确认后才落盘
  - **AI 改写建议**：BYOK 模型只改写既有事实的表述，反编造护栏不过不能采用
  - **导出 Word**：零依赖 `.doc`，方便往网申系统粘贴文本（排版以 PDF 为准）
- **高级模板**（手写 HTML 精排版）：只读浏览与一键生成

底部还有**版本谱系**：哪版简历投了哪些岗位、各走到哪一步。

### 准备

**投递之前**的事归一处——宣讲会、题库与笔记都在这里（2026-09-18 从「进展」页迁来：那页的定位是"投递之后"，这两件恰恰在投递之前）：

- **宣讲会 / 招聘会**：活动时间、形式、地点与收获，可导出 `.ics`（提前 1 小时提醒）；不推进任何阶段。看板「近 7 天宣讲会」点一下直达这里
- **题库**（两个视图）：「我的题库」= 自建可编辑的 `questions.csv`（领域 / 科目 / 状态 `未看·看过·会了` / 答案要点），可从 `03_面试准备/**/*.md` **只读解析 → 预览 → 确认导入**（两段式）；**点任意一行打开详情**，在弹窗里改答案要点、标记三态、调难度——同样先看差异表再确认（确认前不落盘，取消不留痕）；「被问过的」= 面过的问题按公司 + 岗位归集、关键词检索——面试前先过一遍这家公司问过你什么；命令行可 `jobws bank export --csv <文件>` 导出整个题库、`jobws bank import-csv <文件>` 从 CSV 导入（预览后凭令牌落盘；导出再导入是幂等的）、`jobws bank due` 看今日待复习（未看恒在；看过 3 天 / 会了 14 天；空/脏数据保守计待复习）
- **笔记**：`03_面试准备` 与 `04_知识库` 的 Markdown 直接读——左侧目录树（`README` 显示为「目录说明」、`_模板_`/`_示例_` 淡显、空文件与读不了的文件带标记、可按文件名过滤），右侧渲染成正文（标题 / 列表 / **勾选框** / 表格 / 代码块 / 引用），长文右侧有「本页大纲」，超 256 KB 截断并显式告知。改内容用自己的编辑器，切回来 10 秒内自动刷新（并回到原页签与原文件）；**勾选框可点**——点一下弹出「原行 → 新行」差异，确认后只改这一行的一个字符，文件其余内容一个字节都不动（走全站唯一的两段式写通道；预览之后这一行若被改过则拒绝并要求重新预览）；**全文搜索**可按关键词搜文件名与正文，点结果直接打开并滚到命中行（命中过多只列前 50 条并说明；读不动或超过 256 KB 的文件会列出"没搜全"，不静默少给）

### 进展

投递之后的主战场，四个子 Tab：

- **面试**：三段式记录（问题 → 回答要点 → 复盘），48 小时内待定的琥珀高亮，一键导出 `.ics` 日历
- **邮件**：往来邮件台账（面试邀约 / 笔试通知 / 拒信…）——可关联投递记录、标签行内改；有 Message-ID 的邮件给「打开原邮件」（Gmail 搜索深链），无可用深链的邮箱（Outlook / QQ / 163 等）给「复制主题去邮箱搜索」的降级提示；**邮件不会自动改阶段**
- **联系人**：招聘方联系人跟进节奏，超期琥珀提醒，一键「已联系」
- **Offer 对比**：多个 offer 的已知事实并排，**只并排、不推荐**

### 素材库

事实库（`00_事实库/`）的只读浏览（由 CLI / AI 生成维护）：事实卡以正文排版显示（表格 / 勾选框 / 引用 / 代码块），超 256 KB 截断并**显式告知**；外部改完切回来 10 秒内自动刷新。**简历相关文件已迁往「简历工坊」**（2026-09-03），此处不再重复展示。

### 设置（Provider）

导航栏「设置」页配置 AI Provider（BYOK，自带 key）：

- **Base URL**：OpenAI 兼容端点（含 `/v1`，如 `https://api.orcarouter.ai/v1`）
- **API Key**：只存本地，界面只显示脱敏后的末尾 4 位
- **测试连接**：调 `{base_url}/models` 验证 key 有效并列出模型。出网 HTTPS 默认校验证书（抓取 JD、简历改写同一策略）：本机证书库加载失败时会**拒绝连接**并提示修证书库（`certmgr.msc`），不会静默跳过校验——key 不会在未校验的连接上发出。显式降级用 `JOBWS_HTTP_TLS=insecure`（不推荐）
- **数据与隐私**：整包导出 zip、快照备份到系统用户目录、打开数据目录、无遥测声明
- **导成 Obsidian 笔记**（命令行）：`python tools/jobws.py export --obsidian <目录>`——八张 CSV 各成一个目录、**每行一笔记**，frontmatter 带上原表全部字段（供 Obsidian Bases / Dataview 过滤排序），题库笔记带 spaced-repetition 卡片语法；输出目录带时间戳、**不覆盖旧导出**、**不改工作区**（是快照，不是同步）
- **还没有 API Key？**：未存 key 时，页面会给出一个推荐 Provider 的注册入口，以及一个「一键填入该 Provider 端点」的按钮（预设值只在源码里定义一处）。这个入口在界面上明确标注为推广链接——通过它注册会给本项目作者返佣，你的价格与权益不受影响；点击只是打开网页，不会有任何数据从本应用发出。该入口当前指向 [OrcaRouter](https://www.orcarouter.ai/ref/ref_f34ad879f774bce8bc82)。

> 本工作台的 AI 判断默认由 AI CLI（CodeBuddy 等）完成，Provider 是可选的 BYOK 增强入口（简历导入 / AI 改写用）。

### 只读邮箱拉取（可选）

如果你的邮箱支持 IMAP，工作台可以把最近的招聘邮件拉回来，省掉逐封复制粘贴。在**设置页 → 「邮箱只读拉取」**里配置（填 IMAP 授权码，不是网页登录密码；多数邮箱要先在网页版设置里开启 IMAP 服务）。

它怎么工作、以及它不会做什么：

- **只读**：连接使用 `SELECT (readonly)` 与 `BODY.PEEK`——不发信、不标已读、不移动、不删除任何邮件。
- **只在点击时连接**：只有你点「从邮箱拉取」时才会连一次邮箱——没有后台定时器、轮询或连接保活。
- **凭证只存本地，但是明文**：保存在本机 `<工作区>/config/imap.json`，界面与错误消息里脱敏，也**不会进入导出 / 备份 zip**。明文意味着：能读到你用户目录的进程（包括同机的其它程序）都能读到它——这是"不引入系统钥匙串依赖"的取舍。请把工作区当敏感目录看待，不要放在同步盘或公共共享里。
- **默认校验服务器证书**：连接会对邮件服务器证书做系统证书库校验。如果本机 Windows 证书库有损坏条目，`create_default_context()` 会失败、连接被**拒绝**（授权码不能在未校验的连接上传输）。确认了解风险——连接可能被中间人截获——后，可显式设置环境变量 `JOBWS_IMAP_TLS=insecure` 跳过校验。
- **默认 dry-run**：拉取只列出邮件，在你逐条确认建议之前不会往追踪表写任何东西。

常见流程：投递追踪 → 「从邮箱拉取」 → 选时间范围（最近 7 / 30 / 90 天）→ 本地关键词筛选 → 点一封邮件 → 核对解析出的建议 → 确认写回。如果这封邮件对应的投递还没记录，空态里会直接给一个「创建记录」表单（当前阶段默认按邮件内容推断）。

拉取列表里的邮件有**两条去向**：点邮件正文 = 走「解析 → 建议 → 确认」更新投递状态；点右侧的「＋」小图标 = **把这封邮件的元数据记入邮件台账**（主题 / 发件人 / 日期 / Message-ID）——之后到「进展 → 邮件」里补标签与关联，不用再手打一遍。

---

## 四、让 AI 干活：jwb-jd / jwb-apply 工作流

网页负责看和记，**判断类的工作交给 AI**。在 CodeBuddy 里用自然语言：

### 接进别的 AI 宿主（MCP，可选）

工作台还能作为一个 **MCP 服务**接进支持 MCP 的其它 AI 宿主（Claude Code / Codex /
Gemini CLI 等）：AI 能读投递记录、岗位池与看板，并在**你确认之后**写入
（先给差异表，你点头才落盘）。

- 安装与三种宿主的配置形态：`docs/mcp-integration.md`（**配置键名按宿主不同，别照抄**）
- 四个入口（命令行 / AI 宿主 / 编辑器插件 / 桌面界面）各能做什么：`docs/four-ends.md`

### 解析一个岗位（jwb-jd 工作流）

把 JD 原文贴给我，或者说"解析这份 JD"。AI 会：

1. 在 `personal/01_岗位池/<公司>_<岗位>/` 存 JD 原文
2. 跑硬门槛过滤（学历→专业→届数→英语→城市，对照 `personal/AGENTS.md`）
3. 通过后四维度评分（技术30/经历25/方向30/培养15），回查事实卡核验
4. 校验加总并输出档位（75+ 强烈投 / 60-74 投 / 45-59 斟酌 / <45 不投）

**硬门槛不过会直接拦下**，不打分不写材料。比如对外语有硬性要求的岗位会被你的外语红线拦住。

### 生成投递包（jwb-apply 工作流）

说"给 XX 岗位生成投递包"。AI 会：选对应方向的简历版本 → 按需微调四处（项目事实不动）→ 生成 PDF → ATS 校验（页数/文本层/关键事实）→ 归档到 `05_投递追踪/applications/` → 写入追踪表 → 列出改动清单交你确认后 git 提交。

### 更新进展（jwb-track）

面试完说"把 XX 更新到一面"，或直接在网页追踪表里点下拉框。

### 改简历后重新出 PDF（jwb-resume 工作流）

说"重建简历 PDF"，或命令行：

```bash
python tools/jobws.py resume --workspace personal --version hvac
```

---

## 五、CLI 命令速查（不用网页时）

所有命令在仓库根目录执行。`--workspace personal` 可省略（默认就是它）。

```bash
# 追踪表
python tools/jobws.py track list                        # 全部记录
python tools/jobws.py track list --due-within 7         # 未来 7 天到期
python tools/jobws.py track list --stage 笔试           # 按阶段筛
python tools/jobws.py track add --company "某公司" --role "岗位" --direction hvac --batch 正式批 ...
python tools/jobws.py track update --id A001 --stage 一面 --next "准备口述" --next-date 2026-09-10
python tools/jobws.py track history --id A001           # 变更时间线
python tools/jobws.py track import --file 待导入.csv --dry-run   # CSV 批量导入（只预览差异）
python tools/jobws.py track import --file 待导入.csv             # 预览通过后写入
python tools/jobws.py track interview add --app A001 --round 一面 --questions "..."   # 面试记录
python tools/jobws.py track contact add --name "张工" --app A001   # 招聘方联系人
python tools/jobws.py track offer add --company "某公司" --monthly "..."  # Offer 事实
python tools/jobws.py track mail add --subject "面试邀请（一面）" --app A001 --tag 邀约  # 邮件台账
python tools/jobws.py track mail list --app A001        # 某条投递的往来邮件
python tools/jobws.py track check                       # schema 自检（坏文件隔离）

# 投递漏斗看板（Markdown，含周期复盘与失败原因聚类）
python tools/jobws.py report --stdout

# 简历 PDF + ATS 校验
python tools/jobws.py resume --workspace personal            # 全部版本
python tools/jobws.py resume --version hvac                  # 指定版本
python tools/jobws.py resume render --workspace personal     # 数据驱动标准版式
python tools/jobws.py resume render --template std_compact --resume-accent 酒红   # 换版式 + 强调色

# JD 解析卡评分校验
python tools/jobws.py jd "personal/01_岗位池/<目录>/解析卡.md" --domain hvac-cooling --direction hvac
python tools/jobws.py jd --gap --resume hvac "personal/01_岗位池/<目录>/解析卡.md"   # JD↔简历差距
```

> 上文的阶段名（`笔试`、`一面`……）会**原样写进你的数据文件**，所以界面与文档里保留中文；它们按固定词表校验（`STAGES`，定义在 `jobws_core.tracker`），不能简单改成英文。

---

## 六、数据在哪、怎么备份

**所有数据都是纯文本文件**，在 `personal/` 下：

| 目录 | 内容 |
|---|---|
| `00_事实库/` | 项目/实习事实卡——唯一事实源 |
| `01_岗位池/` | 每个岗位一个目录：JD 原文 + 解析卡 |
| `02_简历工坊/` | 简历 md + HTML 模板 + 生成的 PDF + 照片 |
| `03_面试准备/` | 自我介绍、项目表达、题库、行为面、复盘 |
| `04_知识库/` | 知识词典目录——按需自建（骨架里只有一份 README） |
| `05_投递追踪/` | tracker.csv + history.csv（变更时间线）+ interviews / contacts / offers.csv |
| `AGENTS.md` | 你的档案：硬门槛事实、诚实红线 |

**备份（重要）**：`personal/` 已整体 gitignore——**git 不追踪你的数据**，仓库镜像克隆不会带走它们。主备份方式：

1. **设置页「立即备份」**：快照到系统用户目录（工作区之外，推荐，一键完成）
2. **设置页「整包导出 zip」**：随时可带走的完整工作区

> ⚠️ 分享仓库给任何人之前无需担心数据——`personal/` 不在仓库里；但**不要把 `personal/` 目录本身发给别人**（含姓名、照片、联系方式）。

---

## 七、常见问题

### 打开 localhost:5173 黑屏 / 连不上

按顺序排查：

1. **服务活着吗**：`cd web && .\start.ps1` 重启（会自动清端口）。Vite 是前台进程，启动它的终端关了服务就没了——这是最常见原因
2. **浏览器缓存了旧版 JS**：`Ctrl + F5` 强制刷新
3. **还是黑屏**：页面现在有 ErrorBoundary，崩溃会显示错误文字而不是黑屏；按 F12 看 Console，把报错发我

### 启动脚本报错

`start.ps1` 用了三层回退定位仓库根（参数 → 脚本位置 → 向上找 AGENTS.md）。如果报"无法定位仓库根"，在仓库目录内运行，或显式指定：

```powershell
.\start.ps1 -RepoRoot <仓库目录>
```

### npm 命令没反应

Windows 下手动启动前端必须用 `npm.cmd run dev`。直接 `npm run dev` 在某些调用方式下会静默失败（无报错、端口不监听）。

### 端口被占用

`start.ps1` 会自动释放 8765/5173。手动释放：

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### 网页里岗位卡片没有评分

评分必须满足两点：`解析卡.md` 存在 **且** 四项加总与总分自洽（会被 `jd_score` 规则校验）。如果手改过解析卡导致格式不对，网页会当作"未评分"。用 `python tools/jobws.py jd <解析卡路径>` 看具体哪里不自洽。

### CSV 用 Excel 打开乱码

不会乱码——写入用了 UTF-8 BOM（`utf-8-sig`）。如果乱码，说明文件被其他工具重写过编码，联系我修复。

### 双击 exe 没反应

`console=True` 黑窗一闪而过通常意味着**启动即失败**。原因与处置：

1. **端口被占** → exe 现在会给出明确提示并保持窗口（除非被杀软拦截）。先 `Get-NetTCPConnection -LocalPort 8765 -State Listen` 看占用者
2. **刚构建的 exe 数据为空是正常的**——见上文"方式三"（exe 是干净分发物，不读仓库根数据）

### 网页标题显示 "Vite + React + TS"

旧版构建残留的缓存或未刷新产物。`Ctrl+F5` 强刷；仍不行则重新构建前端（`cd web/frontend && npm.cmd run build`）并重启后端。新的正确标题是 "Job Workbench"（窗口标题跟随界面语言，中文界面为「求职工作台」）。

### .ps1 脚本报 ParserError / 中文乱码

含中文的 `.ps1` 必须存成 **UTF-8 带 BOM**。若文件被无 BOM 地重存，Windows PowerShell 5.1 会按 GBK 误解码导致语法错误。两个脚本（`start.ps1`、`build_backend_exe.ps1`）都已带 BOM；手动改它们时**不要去掉 BOM**。

---

## 八、技术文档导航

| 想了解 | 看哪份 |
|---|---|
| 整体架构（三层分离、领域插件） | `docs/specs/2026-08-30-general-workbench-design.md` |
| Web 层设计（API 契约、并发与安全） | `docs/specs/2026-08-30-web-prototype-design.md` |
| AI 工作流定义 | 根 `skills/` 下八个 SKILL.md（五个求职向 + 三个开发向；`tools/jobws.py skills install` 分发到各 AI CLI） |
| 文档总索引 | `docs/README.md` |

---

## 外观：主题与字体

设置页「外观」卡（设备级偏好，只影响这台机器、不随工作区导出）：

- **主题**：默认暗之外内置浅色与 8 套开源皮肤（Catppuccin Mocha·Latte / Nord / Tokyo Night / Rosé Pine + Dawn / Gruvbox / Everforest），支持「跟随系统」；「自定义主题…」改关键色并实时显示对比度，保存后进入主题列表；可导入 tweakcn / shadcn 的 CSS 或导出的 JSON。
- **字体**：界面字体 **12 款**可选（Inter 默认，另有 Geist、IBM Plex Sans、Manrope、Plus Jakarta Sans、DM Sans、Figtree、Outfit、Public Sans、Source Sans 3、Work Sans、Atkinson Hyperlegible，以及系统字体与衬线）；等宽字体**独立**可选 **6 款**（Maple Mono 默认，另有 JetBrains Mono、Fira Code、Geist Mono、IBM Plex Mono、Source Code Pro），管代码 / 编号 / 日期；**数字字体**另设一槽（Geist Mono 默认，可选 JetBrains Mono、IBM Plex Mono 或「跟随界面字体」），管 KPI / 计数 / 天数 / 百分比等数值。全部随应用本地打包（OFL-1.1、离线可用），只含拉丁子集——中文始终走系统栈。**界面字号**为连续滑块（80%–150%，步进 5%）。终端字体请在你的终端软件里设置——`jobws prefs doctor` 会给出推荐清单（Maple Mono / JetBrains Mono / 更纱黑体）。
- **偏好分层**：主题 / 字体是**设备级**（存本机）；`jobws prefs`（theme / font / resume_style）是**工作区级**物料偏好，供 CLI、技能与导出使用。

主题改动会过门禁 `jobws lint themes`（完整性 / 对比度 / 明度阶梯）——10 套内置主题全部满足正文 4.5:1、大字与图形 3:1。
