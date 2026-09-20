# jobws-core

求职工作台的**领域层**：写盘原语、文件锁、路径解析、投递追踪、题库、复盘统计、JD 评分
与两段式写入协议。本地优先，不联网、不上传。

## 它解决什么问题

领域函数原本都在仓库 `tools/` 下，MCP 与桌面端后端靠 `sys.path` 注入 import 它们——
于是 "MCP 必须 editable 安装、仓库必须在侧"。包化之后，领域层是**装上去就能用**的
普通依赖，这条限制才有条件解除（剩余限制见 `docs/mcp-integration.md`）。

## 安装

```bash
pip install -e packages/jobws-core      # 开发（源码形态）
pip install packages/jobws-core         # 或构建 wheel 后安装
```

Python 3.12+（与工作台后端同一基线）。

## import 名为什么是 `jobws_core`

distribution 名是 `jobws-core`，但 **import 名是 `jobws_core`**：`tools/jobws.py`
是 CLI 入口模块，全仓（含 68 个测试）以 `import jobws` 取它——包若同名会抢先命中
包，CLI 调用直接 AttributeError（2026-09-17 实测）。**CLI 模块名优先**。

## 版本

**本包版本是派生物，不是产品版本真值源。** 真值源仍是 `web/electron/package.json`
的 `version`（见 `CONTRIBUTING.md` 与 `tools/release_assist.py`）：构建期由本目录的
`setup.py` 读它写进 wheel 元数据，运行时由 `jobws_core.__version__`
（`importlib.metadata.version("jobws-core")`）读回。二者由 CI 断言一致。

## 边界

**第二批（2026-09-19）加入：**

- `jobws_core.url_infer` / `tls_policy` / `status_parse` 与 `jd_score` / `report` /
  `question_bank`（PR-B）—— 站点 URL 推断、出网 TLS 策略、阶段解析、JD 评分、复盘统计、
  题库。搬完之后**仓库里没有领域实现了**：`tools/` 只剩 CLI、检查器与两个跨端登记的
  入口（见下）。
- `jobws_core.pathres` —— 路径解析。**它不再从 `__file__` 推断应用根**：入口显式
  `set_app_root()`，没注入就报错。住在 `web/backend/` 时「向上三级」正好是仓库根，
  搬进 site-packages 后同一个表达式指向安装目录的上层、数据根静默漂移
  （完整论证见 `tests/test_domain_root.py`）。
- `jobws_core.tracker`（13 个子模块）—— 投递追踪领域层。仓内 `tools/tracker/` 留
  **合并门面 shim**：领域模块经 `sys.modules` 别名指向本包（同一个对象，否则
  monkeypatch 会静默失效），留仓的 `_cli*.py` 挂回 `tracker.*`。
  **CLI 子模块按用户拍板留仓**。
- `jobws_core.approval` —— 两段式写入协议的**外壳**。操作注册表**不在包里**：
  由**调用侧** `register()` 登记，而且**分层**：本包导入时自登记「实现已在包内」的十一个
  （`track.*` / `talk.add` / `mail.add` / `interview.*` / `question.*`），仓库侧的
  `tools/approval.py` 再追加 `prep.toggle` 与 `init`（那两个领域模块按拍板留仓）——
  协议层因此不认识任何具体实现，这是解掉包级循环依赖的关键。

**两批共用的形态：**

- 旧路径留转发 shim 并发出 `DeprecationWarning`，存量调用点零改动。
  `jobws lint legacy-imports` 把旧名 import 数压成**只许下降**的水位，
  **降到 0 就删 shim**——`filelock` / `workspace_io` 已于 2026-09-19 走完这条流程。
- **本地开发注意**：本包若以**非 editable** 形态安装，**新增模块对已装副本不可见**
  （PEP 660 的静态映射）——往包里搬新模块后不重装就会 `ModuleNotFoundError`
  （2026-09-19 A-1 实测）。建议
  `uv pip install -e packages/jobws-core --config-settings editable_mode=compat`：
  compat 模式把 `src` 整体入 path，新文件自动可见。
- **导入 `jobws_core.tracker` 之前必须有应用根**：`tracker/_core.py` 在**导入期**就求值
  `ROOT`（`pathres.resolve_root()`），没注入会抛 `RuntimeError`。宿主进程若只是
  "import 一下看看"（安装冒烟、IDE 索引、静态分析），请先
  `from jobws_core import pathres; pathres.set_app_root(<任意目录>)`——
  CI 的 `install-smoke` 就是这么做的。
