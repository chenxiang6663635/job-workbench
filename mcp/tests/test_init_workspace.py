# -*- coding: utf-8 -*-
"""MCP 侧的首次使用初始化（2026-10-19，阻塞级缺口）。

**要解决的问题**（真机实测）：`dsh-job-workbench` 只装插件时，`<data_root>/personal`
不存在 → `server.main()` 在 `resolve_workspace(must_exist=True)` 处 `return 2`，
**17 个工具一个都不注册**。而 npm 包里**没有 init 入口**（`install.ps1` 只做 pnpm +
装包；工具面里也没有 init）。结果：「独立安装、装着就能用」只对"装过桌面版"的机器成立。

策略（折中，避免静默兜底）：
- **默认数据根**（未设 `JOBWS_DATA_DIR`）+ 工作区缺失 → **自动建空骨架**并说明（零配置可用）；
- **显式**根（设了 `JOBWS_DATA_DIR`）或显式 `--workspace` + 缺失 → **仍然报错**，
  不自动创建（防止把写错的路径悄悄建成工作区）；
- 任何情况下都**不覆盖**已有文件（幂等）。
"""

import os

import pytest

from jobws_mcp import init_workspace, paths, server

MODULES = ("00_事实库", "01_岗位池", "02_简历工坊",
           "03_面试准备", "04_知识库", "05_投递追踪")


def test_template_root_found():
    """模板根必须能从仓库里解析到（打包形态另测）。"""
    root = init_workspace.template_root()
    assert os.path.isdir(os.path.join(root, "workspace")), root
    assert os.path.isfile(os.path.join(root, "AGENTS.example.md")), root


def test_init_creates_skeleton(tmp_path):
    """空目录 → 6 个模块 + README.md + AGENTS.md，且返回创建清单。"""
    target = str(tmp_path / "personal")
    created = init_workspace.init_workspace(target)

    for module in MODULES:
        assert os.path.isdir(os.path.join(target, module)), module
    assert os.path.isfile(os.path.join(target, "README.md"))
    assert os.path.isfile(os.path.join(target, "AGENTS.md"))
    assert created, "应返回创建清单（供 stderr 如实报告）"


def test_init_is_idempotent_and_never_overwrites(tmp_path):
    """已有文件一律不覆盖；第二次什么也不建。"""
    target = str(tmp_path / "personal")
    os.makedirs(target)
    mine = os.path.join(target, "README.md")
    with open(mine, "w", encoding="utf-8", newline="") as fh:
        fh.write("MY OWN NOTES")

    init_workspace.init_workspace(target)
    with open(mine, encoding="utf-8") as fh:
        assert fh.read() == "MY OWN NOTES", "覆盖了用户已有文件"

    second = init_workspace.init_workspace(target)
    assert second == [], "第二次仍报告创建：幂等性坏了"


def test_ensure_auto_inits_default_root(tmp_path, monkeypatch):
    """默认根 + 缺失 → 自动建，并给出**可读的说明**。"""
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setattr(init_workspace.paths, "data_root", lambda: str(tmp_path))

    workspace, notice = init_workspace.ensure_workspace()

    assert workspace == os.path.join(str(tmp_path), "personal")
    assert os.path.isdir(os.path.join(workspace, "05_投递追踪"))
    assert notice and "自动初始化" in notice


def test_ensure_refuses_when_data_root_is_explicit(tmp_path, monkeypatch):
    """显式 JOBWS_DATA_DIR + 缺失 → 报错，不自动建（防止拼错的路径被悄悄建成工作区）。"""
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path / "typo-root"))
    with pytest.raises(paths.WorkspaceError):
        init_workspace.ensure_workspace()
    assert not os.path.isdir(os.path.join(str(tmp_path / "typo-root"), "personal")), \
        "显式根下不应被自动创建"


def test_existing_workspace_is_returned_without_notice(tmp_path, monkeypatch):
    """已初始化 → 原样返回，notice 为空（不打扰）。"""
    os.makedirs(os.path.join(str(tmp_path), "personal"))
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setattr(init_workspace.paths, "data_root", lambda: str(tmp_path))

    workspace, notice = init_workspace.ensure_workspace()
    assert notice is None
    assert workspace == os.path.join(str(tmp_path), "personal")


def test_main_init_flag_writes_to_stderr_and_returns_zero(tmp_path, monkeypatch, capsys):
    """`--init` 显式入口：成功、退出码 0，且**不往 stdout 写**（stdio 是协议通道）。"""
    monkeypatch.setattr(init_workspace.paths, "data_root", lambda: str(tmp_path))

    code = server.main(["--init"])

    assert code == 0
    captured = capsys.readouterr()
    assert captured.out == "", "stdout 被污染，会变成畸形报文"
    assert "已初始化" in captured.err
    assert os.path.isdir(os.path.join(str(tmp_path), "personal", "05_投递追踪"))


def test_main_init_is_idempotent(tmp_path, monkeypatch, capsys):
    """再跑一次 `--init`：不覆盖、退出码 0、如实说"已存在"。"""
    monkeypatch.setattr(init_workspace.paths, "data_root", lambda: str(tmp_path))
    server.main(["--init"])
    capsys.readouterr()

    code = server.main(["--init"])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out == ""
    assert "已存在" in captured.err
