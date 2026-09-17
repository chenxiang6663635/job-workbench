# -*- coding: utf-8 -*-
"""规模预算检查（tools/check_size.py）：把 CONTRIBUTING 第 1 条从软条款变成量具。

钉五件事：
1. **分类正确**——tests/ 与 locales/ 属「数据·声明型」（1500），业务代码属
   「逻辑型」（300）；同阈值会逼人把常量表拆碎；
2. 超限文件与超长函数（>80 行）会被点名；
3. **豁免只许变小**：登记值是水位线，存量可以缩短，不许继续变长；
4. **清单自洁**：已降到阈值以内的条目必须被要求删掉（防清单腐化）；
5. `--staged` 只扫暂存文件——增量守门靠它，否则每次提交都要背全部存量。
"""

import io
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import check_size  # noqa: E402


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """一个最小仓库：只扫 tools/ 与 web/frontend/src/，清单落在临时目录。"""
    root = tmp_path / "repo"
    (root / "tools").mkdir(parents=True)
    (root / "web" / "frontend" / "src").mkdir(parents=True)
    monkeypatch.setattr(check_size, "ROOT", str(root))
    monkeypatch.setattr(check_size, "SCAN_DIRS", ("tools", "web/frontend/src"))
    monkeypatch.setattr(check_size, "ALLOWLIST",
                        str(root / "tools" / "size_allowlist.txt"))
    return root


def _write(path, lines, fn_lines=0):
    """写一个人造源文件；fn_lines>0 时造一个指定行数的函数。"""
    body = ["# -*- coding: utf-8 -*-"]
    if fn_lines:
        body.append("def big():")
        body.extend("    x = %d" % i for i in range(max(1, fn_lines - 1)))
    while len(body) < lines:
        body.append("# filler")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(body[:max(lines, len(body))]) + "\n")


def _allow(text):
    with io.open(check_size.ALLOWLIST, "w", encoding="utf-8") as fh:
        fh.write(text)


def test_classify_splits_logic_and_data():
    assert check_size.classify("tools/tracker.py") == "logic"
    assert check_size.classify("web/backend/routers/progress/questions.py") == "logic"
    assert check_size.classify("tests/test_tracker.py") == "data"
    assert check_size.classify("web/frontend/src/i18n/locales/zh-CN.ts") == "data"
    assert check_size.limit_for("logic") == 300
    assert check_size.limit_for("data") == 1500


def test_oversized_file_and_long_function_are_reported(repo):
    _write(str(repo / "tools" / "big.py"), 320)
    _write(str(repo / "tools" / "fns.py"), 120, fn_lines=95)
    problems = check_size.scan()
    joined = "\n".join(problems)
    assert "big.py：320 行 > 300" in joined, joined
    assert "big()：95 行 > 80" in joined, joined


def test_within_budget_passes(repo):
    _write(str(repo / "tools" / "small.py"), 20)
    _write(str(repo / "tools" / "fns.py"), 60, fn_lines=10)
    assert check_size.scan() == []


def test_allowlist_covers_stock_but_rejects_growth(repo):
    target = str(repo / "tools" / "big.py")
    _write(target, 400)
    _allow("tools/big.py = 400  # 存量，拆分前只许变小\n")
    assert check_size.scan() == [], "登记值覆盖存量时应放行"

    _write(target, 430)
    problems = check_size.scan()
    assert any("不许继续膨胀" in p for p in problems), problems


def test_allowlist_is_self_cleaning(repo):
    """已降到阈值以内的条目必须被要求删掉——留着就是给将来预授权。"""
    _write(str(repo / "tools" / "shrunk.py"), 120)
    _allow("tools/shrunk.py = 400  # 曾超标\n")
    problems = check_size.scan()
    assert any("删掉这一行" in p for p in problems), problems


def test_staged_mode_only_scans_staged_files(repo, monkeypatch):
    _write(str(repo / "tools" / "staged_big.py"), 400)
    _write(str(repo / "tools" / "unstaged_big.py"), 400)
    monkeypatch.setattr(check_size, "staged_files",
                        lambda: ["tools/staged_big.py"])

    problems = check_size.scan(staged=True)
    assert any("staged_big.py" in p for p in problems), problems
    assert not any("unstaged_big.py" in p for p in problems), problems
