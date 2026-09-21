# -*- coding: utf-8 -*-
"""笔记勾选框写回：预览校验、字节级翻转与两段式落盘的钉住用例。

覆盖四组：
1. **预览不落盘**且校验明确（非勾选框行 / 行号越界 / 未知分类 / 路径穿越 /
   超限文件）——失败给**结构化错误码**（`prep.notTaskLine` / `prep.lineOutOfRange` …
   界面按语言渲染，中英各自成句；2026-09-21 批次 C-5 从「统一 prep.toggleFailed +
   中文 reason」演进——后者在英文界面呈"英文前缀 + 中文原因"）；
2. **字节级翻转正确**：LF / CRLF / BOM / `[X]` / `[\t]` / 缩进 / 有序列表 /
   行内第二个 `[ ]` 不动；翻转后除目标行外其余字节逐字一致；
3. **两段式语义**：令牌一次性；预览后文件被改（外部编辑器不拿我们的锁）→
   apply 409 冲突且一个字节都不写；
4. **登记点**：`prep.toggle` 在 approval 注册表、领域层与 web 层 section 映射
   一致、apply 走 `prep` 锁、锁文件被列表遍历排除。
"""

import io
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "web", "backend"))
sys.path.insert(0, os.path.join(ROOT_DIR, "tools"))

import approval  # noqa: E402
import deps  # noqa: E402
import prep_notes  # noqa: E402
import prep_toggle  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

WS = "ws-ok"
PREP_DIR = "03_面试准备"
KB_DIR = "04_知识库"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("JOBWS_DATA_DIR", raising=False)
    monkeypatch.delenv("JOBWS_WORKSPACE", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(deps, "ROOT", str(tmp_path))
    (tmp_path / WS).mkdir()

    import main  # noqa: E402
    return TestClient(main.app)


def _write(tmp_path, rel, content, base=PREP_DIR):
    """在（默认）03_面试准备 下写文件；content 为 bytes 时按二进制写。"""
    path = tmp_path / WS / base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        with io.open(str(path), "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
    return path


def _preview(client, rel, lines, section="interview"):
    """C-1 起端点是 `lines`（逗号分隔）；单行 = 长度 1 的列表。"""
    res = client.get("/api/prep/%s/preview-toggle" % section,
                     params={"ws": WS, "rel": rel, "lines": str(lines)})
    assert res.status_code == 200, res.text
    return res.json()


def _apply(client, token):
    return client.post("/api/approvals/apply", json={"token": token})


# --- 第一组：预览不落盘 + 校验明确 --------------------------------------------


def test_preview_touches_nothing_and_promises_the_diff(client, tmp_path):
    path = _write(tmp_path, "打卡.md", "# 计划\n- [ ] 学习\n- [x] 复习\n")
    before = path.read_bytes()

    data = _preview(client, "打卡.md", 2)

    assert data["token"]
    assert data["expiresAt"]
    assert data["summary"] == "翻转勾选框：打卡.md 第 2 行（未勾选 → 已勾选）"
    assert data["diff"] == ["打卡.md（第 2 行）", "- - [ ] 学习", "+ - [x] 学习"]
    # 预览是"将要落什么"的承诺：文件一个字节都不动
    assert path.read_bytes() == before


def test_preview_rejects_non_task_line(client, tmp_path):
    _write(tmp_path, "x.md", "# t\n普通行\n- 文本 [ ] 行内出现\n")
    for line in (1, 2, 3):
        res = client.get("/api/prep/interview/preview-toggle",
                         params={"ws": WS, "rel": "x.md", "lines": line})
        assert res.status_code == 400, line
        body = res.json()
        assert body["error_code"] == "prep.notTaskLine", line
        assert body["error_params"] == {"line": line, "rel": "x.md"}, line


def test_preview_rejects_line_out_of_range_and_missing(client, tmp_path):
    _write(tmp_path, "x.md", "- [ ] a\n")
    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "x.md", "lines": 99})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "prep.lineOutOfRange"
    assert body["error_params"]["line"] == 99
    # 按 `\n` 切行："- [ ] a\n" 切出两个元素（末尾换行留一个空段）——2 是既有口径
    assert body["error_params"]["total"] == 2

    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "x.md"})
    assert res.status_code == 400
    # C-1 起领域层统一用 `prep.missingLines`（行号是列表；旧码 prep.missingLine
    # 与语言包条目在笔 2 一并删除）
    assert res.json()["error_code"] == "prep.missingLines"


def test_preview_rejects_unknown_section(client):
    res = client.get("/api/prep/nope/preview-toggle",
                     params={"ws": WS, "rel": "x.md", "lines": 1})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "prep.unknownSection"
    assert body["error_params"]["section"] == "nope"


def test_preview_rejects_bad_rel(client, tmp_path):
    _write(tmp_path, "x.md", "- [ ] a\n")
    # 领域层把 `\` 统一归一成 `/` 再切段（前端 walk_files 在 Windows 上产
    # 反斜杠 rel，这里必须两条形态都拒）——穿越语义因此**平台无关**，
    # 与只读端点的「posix 上反斜杠是文件名」分流不同（更严格）。
    for bad in ("../x.md", "..\\x.md", "/etc/passwd", "C:/x.md", "a/../x.md",
                "行为面/../../x.md"):
        res = client.get("/api/prep/interview/preview-toggle",
                         params={"ws": WS, "rel": bad, "lines": 1})
        assert res.status_code == 400, bad
        assert res.json()["error_code"] in ("prep.relativeOnly",
                                            "prep.invalidRel"), bad


def test_preview_rejects_non_markdown(client, tmp_path):
    _write(tmp_path, "x.txt", "- [ ] a\n")
    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "x.txt", "lines": 1})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "prep.notMarkdown"
    assert body["error_params"]["rel"] == "x.txt"


def test_preview_rejects_oversize_file(client, tmp_path):
    # 写路径不做截断读写（截断 + 写回 = 后半文件丢失）——超限在预览期直接拒
    _write(tmp_path, "big.md", b"- [ ] a\n" + b"x" * (prep_notes.MAX_BYTES + 1))
    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "big.md", "lines": 1})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "prep.tooLarge"
    assert body["error_params"]["kb"] == prep_notes.MAX_BYTES // 1024


def test_preview_missing_file(client, tmp_path):
    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "无此文件.md", "lines": 1})
    assert res.status_code == 400
    body = res.json()
    assert body["error_code"] == "prep.fileNotFound"
    assert body["error_params"]["rel"] == "无此文件.md"


# --- 第二组：字节级翻转正确 ---------------------------------------------------


def test_apply_flips_and_keeps_other_bytes(client, tmp_path):
    path = _write(tmp_path, "打卡.md", "# 计划\n- [ ] 学习\n- [x] 复习\n结尾\n")
    token = _preview(client, "打卡.md", 2)["token"]

    res = _apply(client, token)

    assert res.status_code == 200
    body = res.json()
    assert body["written"] == 1
    assert body["summary"] == "已勾选：打卡.md 第 2 行"
    assert path.read_bytes() == "# 计划\n- [x] 学习\n- [x] 复习\n结尾\n".encode("utf-8")


def test_apply_flips_uppercase_and_tab_forms(client, tmp_path):
    path = _write(tmp_path, "x.md", "- [X] a\n- [\t] b\n- [x] c\n")
    # [X] → [ ]（大写归一成空格）
    _apply(client, _preview(client, "x.md", 1)["token"])
    # [\t] → [x]（GFM 允许 tab 表示未勾选）
    _apply(client, _preview(client, "x.md", 2)["token"])
    # [x] → [ ]
    _apply(client, _preview(client, "x.md", 3)["token"])
    assert path.read_bytes() == "- [ ] a\n- [x] b\n- [ ] c\n".encode("utf-8")


def test_crlf_preserved(client, tmp_path):
    path = _write(tmp_path, "crlf.md", b"# t\r\n- [ ] a\r\n- [x] b\r\n")
    _apply(client, _preview(client, "crlf.md", 2)["token"])
    assert path.read_bytes() == b"# t\r\n- [x] a\r\n- [x] b\r\n"


def test_bom_preserved(client, tmp_path):
    path = _write(tmp_path, "bom.md", b"\xef\xbb\xbf# t\n- [ ] a\n")
    _apply(client, _preview(client, "bom.md", 2)["token"])
    assert path.read_bytes() == b"\xef\xbb\xbf# t\n- [x] a\n"


def test_double_toggle_restores(client, tmp_path):
    path = _write(tmp_path, "x.md", "- [ ] a\n")
    for _ in range(2):
        _apply(client, _preview(client, "x.md", 1)["token"])
    assert path.read_bytes() == "- [ ] a\n".encode("utf-8")


def test_knowledge_section_toggle(client, tmp_path):
    path = _write(tmp_path, "速查卡.md", "- [ ] 背八股\n", base=KB_DIR)
    _apply(client, _preview(client, "速查卡.md", 1, section="knowledge")["token"])
    assert path.read_bytes() == "- [x] 背八股\n".encode("utf-8")


def test_flip_unit_forms():
    """纯函数边界：预览与落盘共用这一处，形态钉全。"""
    flip = prep_toggle._flip
    assert flip("- [ ] a")[0] == "- [x] a"
    assert flip("- [X] a")[0] == "- [ ] a"
    assert flip("  - [ ] a")[0] == "  - [x] a"          # 缩进保留
    assert flip("* [ ] a")[0] == "* [x] a"              # * / + 标记
    assert flip("+ [x] a")[0] == "+ [ ] a"
    assert flip("1. [ ] a")[0] == "1. [x] a"            # 有序列表
    assert flip("2) [x] a")[0] == "2) [ ] a"
    assert flip("- [\t] a")[0] == "- [x] a"
    assert flip("- [ ] a [ ] b")[0] == "- [x] a [ ] b"  # 只翻行首第一个
    assert flip("- [ ] a\r")[0] == "- [x] a\r"          # CRLF 行尾残留兼容
    assert flip("- [ ]")[0] == "- [x]"                  # 空任务
    assert flip("- [ ]x")[0] is None                    # 标记后无空白，非 GFM 任务
    assert flip("- 文本 [ ] 后")[0] is None             # 行内出现不翻
    assert flip("普通行")[0] is None
    assert flip("")[0] is None
    assert flip("# [ ] 标题")[0] is None                # 标题不是任务项


# --- 第三组：两段式语义 -------------------------------------------------------


def test_apply_conflict_when_line_changed(client, tmp_path):
    path = _write(tmp_path, "x.md", "- [ ] a\n- [ ] b\n")
    token = _preview(client, "x.md", 2)["token"]
    # 模拟外部编辑器（Obsidian 等不拿我们的锁）在预览后改了这一行
    path.write_bytes("- [ ] a\n- [x] b\n".encode("utf-8"))

    res = _apply(client, token)

    assert res.status_code == 409
    assert res.json()["error_code"] == "approval.conflict"
    # 拒绝时一个字节都不写（保持外部编辑后的内容）
    assert path.read_bytes() == "- [ ] a\n- [x] b\n".encode("utf-8")


def test_apply_conflict_when_line_shifted(client, tmp_path):
    path = _write(tmp_path, "x.md", "# t\n- [ ] a\n")
    token = _preview(client, "x.md", 2)["token"]
    # 行号漂移：顶部插入一行，第 2 行不再是原来的任务行
    path.write_bytes("# t\n插入一行\n- [ ] a\n".encode("utf-8"))
    res = _apply(client, token)
    assert res.status_code == 409
    assert path.read_bytes() == "# t\n插入一行\n- [ ] a\n".encode("utf-8")


def test_token_is_single_use(client, tmp_path):
    _write(tmp_path, "x.md", "- [ ] a\n")
    token = _preview(client, "x.md", 1)["token"]
    assert _apply(client, token).status_code == 200
    res = _apply(client, token)
    assert res.status_code == 422
    assert res.json()["error_code"] == "approval.tokenInvalid"


# --- 第四组：登记点 -----------------------------------------------------------


def test_registry_has_toggle():
    assert approval._OPERATIONS.get("prep.toggle") is prep_toggle.apply_approved_toggle


def test_section_dirs_match_web_layer():
    """领域层 SECTION_DIRS 与 web 层（deps 常量 + routers/prep.py）三处同源。"""
    from routers import prep as prep_router  # noqa: E402

    assert prep_notes.SECTION_DIRS["interview"] == deps.DIR_PREP
    assert prep_notes.SECTION_DIRS["knowledge"] == deps.DIR_KB
    assert prep_router.SECTION_DIRS == prep_notes.SECTION_DIRS


def test_apply_uses_prep_lock(client, tmp_path, monkeypatch):
    """落盘必须在 `prep` 锁内（工作区级互斥；锁文件顺带被创建）。"""
    _write(tmp_path, "x.md", "- [ ] a\n")
    token = _preview(client, "x.md", 1)["token"]
    called = []
    real = prep_toggle._lock_path

    def spy(workspace=None):
        called.append(workspace)
        return real(workspace)

    monkeypatch.setattr(prep_toggle, "_lock_path", spy)
    assert _apply(client, token).status_code == 200
    assert called
    # 锁落在 config（与 imap / provider 同款），不进业务目录
    assert os.path.exists(os.path.join(str(tmp_path / WS), "config", "prep.lock"))


def test_apply_to_knowledge_does_not_create_interview_dir(client, tmp_path):
    """锁与写入目标解耦：工作区里只有 04 时，写回不该凭空建出 03 目录。"""
    path = _write(tmp_path, "速查卡.md", "- [ ] 背八股\n", base=KB_DIR)
    assert not (tmp_path / WS / PREP_DIR).exists()

    _apply(client, _preview(client, "速查卡.md", 1, section="knowledge")["token"])

    assert path.read_bytes() == "- [x] 背八股\n".encode("utf-8")
    assert not (tmp_path / WS / PREP_DIR).exists()
    assert (tmp_path / WS / "config" / "prep.lock").exists()


def test_lock_file_hidden_from_listing(client, tmp_path):
    """锁不进笔记目录的列表（否则界面会多出一行"神秘空文件"）。"""
    _write(tmp_path, "x.md", "- [ ] a\n")
    _write(tmp_path, "y.md", "- [ ] b\n", base=KB_DIR)
    _apply(client, _preview(client, "x.md", 1)["token"])

    for section in ("interview", "knowledge"):
        res = client.get("/api/prep/%s" % section, params={"ws": WS})
        rels = [item["rel"] for item in res.json()["items"]]
        assert ".prep.lock" not in rels


# --- 第五组：批量翻转（C-1，2026-09-21）---------------------------------------
#
# 直接调领域层（不绕 HTTP）——批量是载荷形态的扩展，端点改造是后一笔；走 HTTP
# 的既有四组在笔 2 之后覆盖同一份语义。分叉定案：整批原子（3=A）、上限 100（4）、
# 老单行载荷显式兼容（5=A）。


def test_preview_batch_lists_every_line_and_touches_nothing(client, tmp_path):
    path = _write(tmp_path, "打卡.md",
                 "# 计划\n- [ ] 学习\n- [x] 复习\n- [ ] 复盘\n")
    before = path.read_bytes()

    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "打卡.md", [2, 3])

    assert errors == []
    assert plan["payload"]["lines"] == [
        {"line": 2, "expected": "- [ ] 学习"},
        {"line": 3, "expected": "- [x] 复习"}]
    # diff = N 个既有 3 行块平铺（块间空一行）
    assert plan["diff"] == ["打卡.md（第 2 行）", "- - [ ] 学习", "+ - [x] 学习", "",
                            "打卡.md（第 3 行）", "- - [x] 复习", "+ - [ ] 复习"]
    assert plan["summary"] == "翻转勾选框：打卡.md 第 2、3 行（2 项）"
    # 预览是承诺：一个字节都不动
    assert path.read_bytes() == before


def test_preview_single_line_keeps_existing_wording(client, tmp_path):
    """N=1 是批量的特例：文案与现状**逐字**相同（老界面与既有用例不受影响）。"""
    _write(tmp_path, "打卡.md", "# 计划\n- [ ] 学习\n")

    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "打卡.md", [2])

    assert errors == []
    assert plan["diff"] == ["打卡.md（第 2 行）", "- - [ ] 学习", "+ - [x] 学习"]
    assert plan["summary"] == "翻转勾选框：打卡.md 第 2 行（未勾选 → 已勾选）"


def test_apply_batch_writes_once_and_counts(client, tmp_path):
    path = _write(tmp_path, "打卡.md", "# 计划\n- [ ] 学习\n- [x] 复习\n结尾\n")

    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "打卡.md", [2, 3])
    result = prep_toggle.apply_approved_toggle(plan["payload"], str(tmp_path / WS))

    assert result["written"] == 2
    assert result["summary"] == "已写回：打卡.md 2 行（勾选 1、取消 1）"
    assert path.read_bytes() == "# 计划\n- [x] 学习\n- [ ] 复习\n结尾\n".encode("utf-8")


def test_apply_batch_rejects_all_when_one_row_changed(client, tmp_path):
    """分叉 3=A：任一不符 → 整批拒绝、零字节写入（不做"翻能翻的"）。"""
    path = _write(tmp_path, "x.md", "- [ ] a\n- [ ] b\n- [ ] c\n")
    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "x.md", [1, 2, 3])
    # 模拟外部编辑器（不拿我们的锁）在预览后改了中间一行
    path.write_bytes("- [ ] a\n- [x] b\n- [ ] c\n".encode("utf-8"))
    before = path.read_bytes()

    with pytest.raises(prep_toggle.tracker.ConflictError) as exc:
        prep_toggle.apply_approved_toggle(plan["payload"], str(tmp_path / WS))

    assert "第 2 行" in str(exc.value)
    assert path.read_bytes() == before


def test_apply_accepts_legacy_single_payload(client, tmp_path):
    """分叉 5=A：老形态载荷（line / expected 单数字段）仍落盘。

    钉这个是因为最坏形态不是报错——是 `payload.get("lines") or []` 得到空列表、
    循环零次、返回"成功翻转 0 行"：用户确认了却什么都没写。
    """
    path = _write(tmp_path, "x.md", "- [ ] a\n")

    result = prep_toggle.apply_approved_toggle(
        {"section": "interview", "rel": "x.md", "line": 1,
         "expected": "- [ ] a"}, str(tmp_path / WS))

    assert result["written"] == 1
    assert path.read_bytes() == "- [x] a\n".encode("utf-8")


def test_preview_rejects_duplicate_empty_and_too_many_lines(client, tmp_path):
    _write(tmp_path, "x.md", "- [ ] a\n- [ ] b\n")
    # 重复行号：不静默去重（哪条被吞了用户无从知晓）
    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "x.md", [1, 1])
    assert plan is None
    assert errors[0][0] == "prep.duplicateLine"
    assert errors[0][1]["line"] == 1
    # 空：没给行号
    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "x.md", [])
    assert plan is None
    assert errors[0][0] == "prep.missingLines"
    # 超上限（防御性：正常清单 10-30 行）
    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "x.md",
                                             list(range(1, 102)))
    assert plan is None
    assert errors[0][0] == "prep.tooManyLines"
    assert errors[0][1]["limit"] == 100


def test_endpoint_accepts_lines_csv(client, tmp_path):
    """端点只做「字符串 → int 列表」解析，业务校验全在领域层。"""
    _write(tmp_path, "打卡.md", "# 计划\n- [ ] 学习\n- [x] 复习\n")

    res = client.get("/api/prep/interview/preview-toggle",
                     params={"ws": WS, "rel": "打卡.md", "lines": "2,3"})

    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert body["summary"] == "翻转勾选框：打卡.md 第 2、3 行（2 项）"
    assert body["diff"] == ["打卡.md（第 2 行）", "- - [ ] 学习", "+ - [x] 学习", "",
                            "打卡.md（第 3 行）", "- - [x] 复习", "+ - [ ] 复习"]


def test_endpoint_rejects_unparsable_lines(client, tmp_path):
    _write(tmp_path, "x.md", "- [ ] a\n- [ ] b\n")
    for bad in ("a", "2,", ",2", "2,,3", "1.5", "二"):
        res = client.get("/api/prep/interview/preview-toggle",
                         params={"ws": WS, "rel": "x.md", "lines": bad})
        assert res.status_code == 400, bad
        body = res.json()
        assert body["error_code"] == "prep.invalidLines", bad
        assert body["error_params"]["lines"] == bad, bad


def test_preview_reports_which_line_is_bad(client, tmp_path):
    """逐行校验：哪一行不行就报哪一行（含糊失败比明确报错更贵）。"""
    _write(tmp_path, "x.md", "- [ ] a\n普通行\n")

    errors, plan = prep_toggle.preview_toggle(str(tmp_path / WS), "interview", "x.md", [1, 2])

    assert plan is None
    assert errors[0][0] == "prep.notTaskLine"
    assert errors[0][1]["line"] == 2
