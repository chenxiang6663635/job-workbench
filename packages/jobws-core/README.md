# jobws-core

求职工作台的**领域层**：写盘原语与文件锁。本地优先，不联网、不上传。

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

- 本批（2026-09-17）只含两个零依赖叶子：`jobws_core.filelock`、`jobws_core.workspace_io`。
- 旧路径 `tools/filelock.py` / `tools/workspace_io.py` 保留为**转发 shim**并发出
  `DeprecationWarning`——存量调用点零改动，下一版删 shim。
- 领域层主体（`tools/tracker/`）与协议层 `tools/approval.py` 的搬迁在后续批次。
