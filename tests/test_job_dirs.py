# -*- coding: utf-8 -*-
"""岗位池目录的删除与改名（批 D 数据安全网）：领域层 + HTTP 端点。

钉住五件事（语义与 CSV 表删除同族，载体是目录）：
1. **预览不落盘**：目录一个字节不动；差异表列出目录内全部文件（"将失去什么"）；
2. **目录级留痕**：删前整个目录复制到**工作区之外**，且快照目录树与源一致
   （可整份拷回）；写不出即**中止删除**；
3. **预览后变了就拒**：文件清单不符（新增 / 删除 / 大小变）→ 409 类冲突、零改动；
4. **改名可逆**：`os.rename` + JD 首行标题同步（只动首行，其余内容一字不动）；
   新名被占 / 同名是错误；
5. **路径守卫**：目录名含 `/`、`\\`、`..` 一律拒（删除比读取更不可逆）。
"""

import csv
import io
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import deps  # noqa: E402
from jobws_core import job_dirs  # noqa: E402
from jobws_core import job_rename  # noqa: E402
from jobws_core import tracker  # noqa: E402

WS = "ws-ok"
JOB_NAME = "示例科技_后端开发"


def _seed_job(ws, name, files):
    """建一个岗位目录；files = {相对路径: 内容}。"""
    base = os.path.join(ws, "01_岗位池", name)
    for rel, content in files.items():
        full = os.path.join(base, *rel.split("/"))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with io.open(full, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return base


def _tree(job_dir):
    """目录内的相对路径清单（快照与源的一致性对比用）。"""
    out = []
    for dirpath, _dirnames, filenames in os.walk(job_dir):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            out.append(os.path.relpath(full, job_dir).replace("\\", "/"))
    return sorted(out)


@pytest.fixture()
def ws(tmp_path):
    path = tmp_path / "ws"
    (path / "01_岗位池").mkdir(parents=True)
    (path / "05_投递追踪").mkdir(parents=True)
    return str(path)


@pytest.fixture()
def outside(tmp_path, monkeypatch):
    """把留痕根钉到临时目录：不污染真实快照区，又能断言「在工作区之外」。"""
    root = tmp_path / "snapshots"
    monkeypatch.setattr(job_dirs.pathres, "snapshot_root", lambda: str(root))
    return str(root)


# --- 第一组：目录名生成 / 拆分 / 守卫 -----------------------------------------


def test_build_and_split_are_inverse():
    name, error = job_dirs.build_dir_name("示例科技", "后端开发")
    assert error is None
    assert name == "示例科技_后端开发"
    assert job_dirs.split_dir_name(name) == ("示例科技", "后端开发")


def test_build_rejects_invalid_chars_and_empty():
    name, error = job_dirs.build_dir_name("示/例", "后端")
    assert name is None and "非法字符" in error
    name, error = job_dirs.build_dir_name("", "")
    assert name is None and "不能为空" in error


@pytest.mark.parametrize("bad", ["../x", "a/b", "a\\b", "C:name", "..", ""])
def test_safe_name_guard_rejects_path_tricks(ws, bad):
    errors, plan = job_dirs.preview_delete_job(bad, ws)
    assert plan is None
    assert errors


# --- 第二组：删除（预览 / 快照 / 冲突 / 中止）--------------------------------


def test_preview_delete_lists_files_and_linked_applications(ws, outside):
    job_dir = _seed_job(ws, JOB_NAME, {
        "JD原文.md": "# 示例科技 后端开发\n\n正文\n",
        "解析卡.md": "评分：80\n",
        "材料/我的笔记.md": "笔记\n",
    })
    rows = [dict((field, "") for field in tracker.FIELDS)]
    rows[0].update({"id": "A001", "公司": "示例科技", "岗位": "后端开发",
                    "当前阶段": "已投"})
    tracker.write_rows(rows, ws)
    before = _tree(job_dir)

    errors, plan = job_dirs.preview_delete_job(JOB_NAME, ws)

    assert errors == []
    diff = "\n".join(plan["diff"])
    assert "JD原文.md" in diff and "解析卡.md" in diff and "材料/我的笔记.md" in diff
    assert "1 条投递关联此岗位" in diff and "A001" in diff
    assert plan["payload"]["name"] == JOB_NAME
    # 预览不落盘
    assert _tree(job_dir) == before


def test_apply_delete_snapshots_and_removes(ws, outside):
    job_dir = _seed_job(ws, JOB_NAME, {
        "JD原文.md": "# 示例科技 后端开发\n",
        "解析卡.md": "评分：80\n",
    })
    errors, plan = job_dirs.preview_delete_job(JOB_NAME, ws)

    result = job_dirs.apply_approved_job_delete(plan["payload"], ws)

    assert result["written"] == 1
    assert not os.path.exists(job_dir)
    # 留痕是完整目录树，且在工作区之外
    trace = result["trace"]
    assert os.path.isdir(trace)
    assert not os.path.abspath(trace).startswith(os.path.abspath(ws) + os.sep)
    assert _tree(trace) == ["JD原文.md", "解析卡.md"]


def test_apply_delete_conflict_when_dir_changed(ws, outside):
    job_dir = _seed_job(ws, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n"})
    errors, plan = job_dirs.preview_delete_job(JOB_NAME, ws)
    # 预览后目录里多了一个文件（外部编辑器 / 同步工具）
    with io.open(os.path.join(job_dir, "新材料.md"), "w", encoding="utf-8") as handle:
        handle.write("x\n")

    with pytest.raises(tracker.ConflictError):
        job_dirs.apply_approved_job_delete(plan["payload"], ws)

    # 一个字节都不动
    assert os.path.isfile(os.path.join(job_dir, "新材料.md"))


def test_apply_delete_aborts_when_snapshot_cannot_be_written(ws, tmp_path, monkeypatch):
    job_dir = _seed_job(ws, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n"})
    errors, plan = job_dirs.preview_delete_job(JOB_NAME, ws)
    # 把留痕根指到一个「文件」上：makedirs 必失败（NotADirectoryError ⊂ OSError）
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir", encoding="utf-8")
    monkeypatch.setattr(job_dirs.pathres, "snapshot_root", lambda: str(blocker))

    with pytest.raises(tracker.ConflictError):
        job_dirs.apply_approved_job_delete(plan["payload"], ws)

    assert os.path.isdir(job_dir)  # 目录原样


# --- 第三组：改名（目录 + JD 首行同步）----------------------------------------


def test_preview_rename_lists_target_and_jd_title(ws, outside):
    _seed_job(ws, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n\n正文\n"})

    errors, plan = job_rename.preview_rename_job(JOB_NAME, "示例科技", "平台开发", ws)

    assert errors == []
    diff = "\n".join(plan["diff"])
    assert "- %s" % JOB_NAME in diff
    assert "+ 示例科技_平台开发" in diff
    assert "- # 示例科技 后端开发" in diff
    assert "+ # 示例科技 平台开发" in diff
    assert plan["payload"]["new_name"] == "示例科技_平台开发"


def test_preview_rename_rejects_existing_target(ws, outside):
    _seed_job(ws, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n"})
    _seed_job(ws, "示例科技_平台开发", {"JD原文.md": "# 示例科技 平台开发\n"})

    errors, plan = job_rename.preview_rename_job(JOB_NAME, "示例科技", "平台开发", ws)

    assert plan is None
    assert any("已存在" in error for error in errors)


def test_apply_rename_moves_dir_and_updates_jd_title_only(ws, outside):
    job_dir = _seed_job(ws, JOB_NAME, {
        "JD原文.md": "# 示例科技 后端开发\n\n正文第一行\n正文第二行\n",
        "解析卡.md": "评分：80\n",
    })
    errors, plan = job_rename.preview_rename_job(JOB_NAME, "示例科技", "平台开发", ws)

    result = job_rename.apply_approved_job_rename(plan["payload"], ws)

    assert result["written"] == 1
    assert "已改名：%s → 示例科技_平台开发" % JOB_NAME in result["summary"]
    assert not os.path.exists(job_dir)
    new_dir = os.path.join(ws, "01_岗位池", "示例科技_平台开发")
    assert os.path.isdir(new_dir)
    # JD 只动首行：标题换新、其余内容一字不动
    with io.open(os.path.join(new_dir, "JD原文.md"), encoding="utf-8") as handle:
        text = handle.read()
    assert text == "# 示例科技 平台开发\n\n正文第一行\n正文第二行\n"
    # 其它文件原样
    assert os.path.isfile(os.path.join(new_dir, "解析卡.md"))


def test_apply_rename_keeps_jd_when_first_line_not_a_title(ws, outside):
    """首行不是 `# 标题` 就不动它（用户手动改过格式——宁可不改，不猜）。"""
    _seed_job(ws, JOB_NAME, {"JD原文.md": "随手记：正文\n"})
    errors, plan = job_rename.preview_rename_job(JOB_NAME, "示例科技", "平台开发", ws)
    assert "- # 示例科技 后端开发" not in "\n".join(plan["diff"])

    job_rename.apply_approved_job_rename(plan["payload"], ws)

    new_dir = os.path.join(ws, "01_岗位池", "示例科技_平台开发")
    with io.open(os.path.join(new_dir, "JD原文.md"), encoding="utf-8") as handle:
        assert handle.read() == "随手记：正文\n"


# --- 第四组：HTTP 端点（契约 + 端到端）---------------------------------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def test_api_preview_delete_and_rename_contract(client, tmp_path, outside):
    ws_dir = str(tmp_path / WS)
    _seed_job(ws_dir, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n"})

    res = client.get("/api/jobs/preview-delete",
                     params={"ws": WS, "name": JOB_NAME})
    assert res.status_code == 200, res.text
    assert JOB_NAME in res.json()["summary"]

    res = client.get("/api/jobs/preview-rename",
                     params={"ws": WS, "name": JOB_NAME,
                             "company": "示例科技", "role": "平台开发"})
    assert res.status_code == 200, res.text
    assert "示例科技_平台开发" in res.json()["summary"]

    # 找不到 → 稳定错误码
    res = client.get("/api/jobs/preview-delete", params={"ws": WS, "name": "无此岗"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "job.deleteFailed"
    res = client.get("/api/jobs/preview-rename",
                     params={"ws": WS, "name": "无此岗",
                             "company": "A", "role": "B"})
    assert res.status_code == 400
    assert res.json()["error_code"] == "job.renameFailed"


def test_api_delete_end_to_end_with_trace(client, tmp_path, outside):
    """端到端：预览令牌 → 唯一落盘通道 → 目录删了、快照在工作区之外。"""
    ws_dir = str(tmp_path / WS)
    _seed_job(ws_dir, JOB_NAME, {"JD原文.md": "# 示例科技 后端开发\n"})
    token = client.get("/api/jobs/preview-delete",
                       params={"ws": WS, "name": JOB_NAME}).json()["token"]

    res = client.post("/api/approvals/apply", json={"token": token})

    assert res.status_code == 200
    body = res.json()
    assert body["written"] == 1
    assert body["trace"]
    assert not os.path.abspath(body["trace"]).startswith(
        os.path.abspath(ws_dir) + os.sep)
    assert not os.path.exists(os.path.join(ws_dir, "01_岗位池", JOB_NAME))
