# -*- coding: utf-8 -*-
"""`init_workspace` 的覆盖保护与目标约束（审计 P0-5）。

背景：`--force --demo` 会把占位数据覆盖到既有文件上——落到真实工作区就是
**数据丢失**，而旧行为把覆盖清单放在落盘**之后**才打印。修复后：
  ① 覆盖清单在写入**前**展示，并要求确认（TTY 下输 yes；非 TTY 必须显式 --yes）；
  ② `--target` 只允许落在**数据根**之内（绝对路径 / `..` 逃逸拒绝；B4 整改 A
  把锚从应用根改为数据根——与 API / MCP 的默认工作区同源）。
"""

import importlib
import io
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

init_workspace = importlib.import_module("init_workspace")


def _run(argv, monkeypatch, capsys, root=None, tty=False, answers=()):
    """直跑 main()：monkeypatch sys.argv（可选连 ROOT 一起指到 tmp），
    返回 (退出码, stdout, 输入序列)。root=None 表示保留真实仓库根。"""
    inputs = list(answers)
    argv = list(argv)
    if argv and argv[0] == "init":
        # jobws 统一入口的子命令名；直跑本模块 main() 不需要这个位置参数
        argv = argv[1:]
    monkeypatch.setattr(sys, "argv", ["init_workspace.py"] + argv)
    if root is not None:
        monkeypatch.setattr(init_workspace, "ROOT", root)
        # B4 整改 A：`--target` 现在锚**数据根**——把数据根钉到同一处，
        # 目标解析与守卫才落在测试构造的目录里。
        monkeypatch.setenv("JOBWS_DATA_DIR", root)
    monkeypatch.setattr("builtins.input", lambda prompt="": inputs.pop(0) if inputs else "")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)
    code = init_workspace.main()
    return code, capsys.readouterr().out, inputs


@pytest.fixture(autouse=True)
def _never_touch_real_data_root(tmp_path, monkeypatch):
    """防呆（2026-10-05 事故后加）：本模块任何用例**不得**落到真实数据根。

    事故复盘：三支用例曾漏传 `root=`——`init --demo --force --yes` 沿
    `resolve_workspace_root` 的真实 legacy 解析落到 `<仓库>/personal`，
    把 7 张真实表覆盖成 demo 内容（已从 9-26 全量快照逐字节恢复，僵尸
    demo 文件已移出）。本 fixture 把数据根**兜底**钉到 tmp：用例显式传
    `root=` 时仍以显式值为准（`_run` 里的 setenv 后执行），漏传时最坏也
    只写测试自己的 tmp。
    """
    monkeypatch.setenv("JOBWS_DATA_DIR", str(tmp_path))


@pytest.fixture()
def realish_ws(tmp_path, monkeypatch):
    """把模块的 ROOT 指到 tmp，并在里面放一个「已填真实数据」的工作区。"""
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setattr(init_workspace, "ROOT", str(root))
    ws = root / "personal"
    (ws / "05_投递追踪").mkdir(parents=True)
    with io.open(os.path.join(str(ws), "05_投递追踪", "tracker.csv"), "w",
                 encoding="utf-8-sig", newline="") as handle:
        handle.write("真实数据，不是 demo\n")
    return str(root)


def test_force_demo_without_yes_is_refused_on_non_tty(realish_ws, monkeypatch, capsys):
    """非交互环境（脚本 / CI）没有确认渠道：未显式 --yes 一律拒绝，数据不动。"""
    code, out, _ = _run(["init", "--target", "personal", "--demo", "--force"],
                        monkeypatch, capsys, root=realish_ws, tty=False)

    assert code == 1, out
    assert "将覆盖" in out, out
    assert "--yes" in out, out
    with io.open(os.path.join(realish_ws, "personal", "05_投递追踪", "tracker.csv"),
                 encoding="utf-8-sig") as handle:
        assert handle.read() == "真实数据，不是 demo\n", "拒绝后一个字节都不许动"


def test_force_demo_with_yes_overwrites(realish_ws, monkeypatch, capsys):
    code, out, _ = _run(["init", "--target", "personal", "--demo", "--force", "--yes"],
                        monkeypatch, capsys, root=realish_ws, tty=False)

    assert code == 0, out
    with io.open(os.path.join(realish_ws, "personal", "05_投递追踪", "tracker.csv"),
                 encoding="utf-8-sig") as handle:
        content = handle.read()
    assert "真实数据" not in content, "已按 --yes 语义覆盖"
    assert "id" in content or "公司" in content, "tracker.csv 应已是 demo 表头"


def test_force_demo_tty_confirmation_cancelled(realish_ws, monkeypatch, capsys):
    code, out, _ = _run(["init", "--target", "personal", "--demo", "--force"],
                        monkeypatch, capsys, root=realish_ws, tty=True, answers=["no"])

    assert code == 1, out
    assert "已取消" in out, out
    with io.open(os.path.join(realish_ws, "personal", "05_投递追踪", "tracker.csv"),
                 encoding="utf-8-sig") as handle:
        assert "真实数据" in handle.read()


def test_target_must_stay_inside_data_root(monkeypatch, capsys, tmp_path):
    """`--target` 的绝对路径 / `..` 逃逸拒绝（审计 P0-5）：初始化不许落出数据根。

    显式锚一个独立数据根（root=tmp/repo）——防呆 fixture 的兜底 tmp 会把
    `outside` 包进来，那样就不是「逃逸」了。
    """
    root = tmp_path / "repo"
    root.mkdir()
    code, out, _ = _run(["init", "--target", os.path.join(str(tmp_path), "outside"),
                         "--force", "--yes"],
                        monkeypatch, capsys, root=str(root), tty=False)

    assert code == 1, out
    assert "数据根" in out, out
    assert not os.path.exists(os.path.join(str(tmp_path), "outside"))


def _make_dir_symlink_or_skip(link, target):
    """建目录链接（symlink；Windows 无特权时回退 junction），都不行才跳过并明说。"""
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        import subprocess
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                capture_output=True)
        if result.returncode == 0:
            return
    pytest.skip("本机不能创建目录符号链接 / junction：%s -> %s" % (link, target))


def test_target_symlink_escape_rejected(monkeypatch, capsys, tmp_path):
    """数据根内指向外的链接同样拒绝（realpath 后判定）——在既有的
    「绝对路径 / `..` 逃逸」之外补链接形态。"""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("原样", encoding="utf-8")
    _make_dir_symlink_or_skip(root / "escape", outside)

    code, out, _ = _run(["init", "--target", "escape", "--force", "--yes"],
                        monkeypatch, capsys, root=str(root))

    assert code == 1, out
    assert "数据根" in out, out
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "原样"


def test_target_equals_data_root_is_not_path_rejected(realish_ws, monkeypatch, capsys):
    """`--target .`（等于数据根）是既有口径：由「已存在且不为空」挡下，
    而不是「必须在数据根之内」——收编到原语时用 is_within_or_equal 保住的语义。

    （`is_within` 排除「恰好等于根」，与本处口径不同——误用它这条会红。）
    """
    code, out, _ = _run(["init", "--target", "."], monkeypatch, capsys, root=realish_ws)

    assert code == 1, out
    assert "已存在且不为空" in out, out
    assert "数据根" not in out, out
