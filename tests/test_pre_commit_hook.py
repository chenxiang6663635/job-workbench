# -*- coding: utf-8 -*-
"""`## .githooks/pre_commit.py` 的隐私护栏（纯判定部分 + CI 入口）。

为什么单独测它：这条护栏的判定此前只能靠"提交时碰巧触发"，而它拦的是
`personal/` 与真实联系方式——一旦漏掉，泄出去的东西撤不回来。判定做成纯函数
（`privacy_problem(paths, diff)`）后，本地钩子与 CI 的第二道闸共用同一份实现，
测试只要钉住这一份即可。

CI 入口单独钉一条：`--no-verify` 是有意保留的逃生口，但它会连带跳过本地护栏——
这一条保证 PR 的完整 diff 仍被同一实现过一遍。
"""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK_PATH = os.path.join(ROOT, ".githooks", "pre_commit.py")

# 样本**拼接构造**而不是写字面量：本文件自己也会过隐私护栏，一个成型的 11 位号码
# 会让护栏朝自己开火（CONTRIBUTING「测试样本拼接构造」同款理由）。
REAL_LOOKING_PHONE = "138" + "1" + "2345678"
PLACEHOLDER_PHONE = "138" + "0000000" + "0"


def _load_hook():
    spec = importlib.util.spec_from_file_location("pre_commit_hook", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_phone_number_is_flagged():
    hook = _load_hook()
    diff = "+ 联系方式：%s（同事手机号）\n" % REAL_LOOKING_PHONE
    assert hook.privacy_problem(["docs/x.md"], diff) is not None


def test_placeholder_numbers_pass():
    """占位号要放行：文档与模板里规范推荐的就是 13800000000 这种。"""
    hook = _load_hook()
    assert hook.privacy_problem(
        ["docs/x.md"], "+ 示例号：%s\n" % PLACEHOLDER_PHONE) is None
    # 末八位全同的号也是占位写法（13888888888）
    assert hook.privacy_problem(
        ["docs/x.md"], "+ 示例号：13888888888\n") is None


def test_hash_fragment_is_not_flagged():
    """锁文件里的长 hash 段含 11 位数字形态 → 不是电话（2026-09-25 收口批）。

    真实案例：`mcp/uv.lock` 的 cffi wheel URL 内嵌 sha256——其中连续的
    数字段与手机号形态完全相同，同时拦住了本地 pre-commit 与 CI privacy
    步骤（为免本说明自身触发护栏，此处不复述号码；实际片段见下方 fragment
    字面量，它的完整走线就是被豁免的对象）。真号码两侧几乎不可能同时是
    hex 字符，故规则：**匹配所在的连续 hex 段 ≥ 32 → 判为 hash**。

    注意本片段的字面量必须写成**单行完整串**：拆行会切断 hex 段、让豁免失效
    （豁免判定的"上下文"就是所在行文本）；本文件自身也过隐私护栏，这段字面量
    正是豁免对象——它此前会让本文件无法提交、也无法通过 CI 的 privacy 步骤。
    """
    hook = _load_hook()
    fragment = "ad28bd19f77047a03084424fbd4cbe997303267c14423737324be0385d"
    diff = ('+    url = "https://files.pythonhosted.org/packages/%s'
            '/cffi-2.1.1-cp312.whl"\n') % fragment
    assert hook.privacy_problem(["mcp/uv.lock"], diff) is None


def test_phone_next_to_short_hex_is_still_flagged():
    """豁免只覆盖「长 hash 段」——短 hex 前缀旁的号码仍要拦（行为锁）。"""
    hook = _load_hook()
    diff = "+ id=abc%s 是同事手机号\n" % REAL_LOOKING_PHONE
    assert hook.privacy_problem(["docs/x.md"], diff) is not None


def test_personal_path_is_flagged():
    hook = _load_hook()
    assert hook.privacy_problem(["personal/简历.md"], "+ 无联系方式\n") is not None


def test_real_email_is_flagged():
    hook = _load_hook()
    # 同样拼接构造：写整串会让这个测试文件自己被护栏拦下
    mailbox = "some" + "one@" + "qq" + ".com"
    assert hook.privacy_problem(["docs/x.md"], "+ 联系：%s\n" % mailbox) is not None


def test_deleted_lines_are_not_flagged():
    """只扫 `+` 行：删除真实号码的**清理类提交**不能被自己的护栏拦死。"""
    hook = _load_hook()
    assert hook.privacy_problem(
        ["docs/x.md"], "- 联系方式：%s\n" % REAL_LOOKING_PHONE) is None


def test_ci_mode_returns_one_when_the_diff_has_a_real_number(monkeypatch, capsys):
    """CI 入口：命中就退出 1——这是 `--no-verify` 之后唯一还站着的那道闸。"""
    hook = _load_hook()

    def _stub(_base):
        return "possible real phone number in staged diff: %s" % REAL_LOOKING_PHONE

    monkeypatch.setattr(hook, "check_privacy_ci", _stub)
    assert hook.main(["--privacy-ci", "origin/main"]) == 1
    assert "privacy" in capsys.readouterr().out


def test_ci_mode_returns_zero_on_clean_diff(monkeypatch, capsys):
    """否定验证：干净 diff 不能因为入口改了就一律非零（那会让 CI 永久红）。"""
    hook = _load_hook()
    monkeypatch.setattr(hook, "check_privacy_ci", lambda _base: None)
    assert hook.main(["--privacy-ci"]) == 0
    assert "OK" in capsys.readouterr().out


# ---- CI 入口的真身（上面那两条把它 monkeypatch 掉了）----------------------------
#
# 只测"分发与退出码"是不够的：CI 闸唯一真正会出错的地方是**那两个 git 调用**
# （浅克隆里 base 取不到、base 为空串导致 diff 恒空）——正是批末独立审查揪出来的
# 两处。所以这里造一个真仓库，走真 `git diff`。

import subprocess  # noqa: E402


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True)


def _seed_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "notes.md").write_text("首页\n", encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "first")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    return repo, base


def test_ci_mode_finds_a_number_in_the_real_diff(tmp_path, monkeypatch):
    hook = _load_hook()
    repo, base = _seed_repo(tmp_path)
    (repo / "notes.md").write_text(
        "首页\n联系：%s\n" % REAL_LOOKING_PHONE, encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "second")

    monkeypatch.chdir(repo)  # 钩子里的 git 调用不带 cwd，跟着进程走

    assert hook.check_privacy_ci(base) is not None


def test_ci_mode_is_clean_when_the_diff_is_clean(tmp_path, monkeypatch):
    """否定验证：真 diff 也认「干净」——否则 CI 会永久红，闸门等于废掉。"""
    hook = _load_hook()
    repo, base = _seed_repo(tmp_path)
    (repo / "notes.md").write_text("首页\n示例号：%s\n" % PLACEHOLDER_PHONE,
                                  encoding="utf-8")
    _git(repo, "add", "notes.md")
    _git(repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
         "commit", "-qm", "second")

    monkeypatch.chdir(repo)

    assert hook.check_privacy_ci(base) is None


def test_ci_mode_fails_loud_when_base_is_missing(tmp_path, monkeypatch):
    """浅克隆场景：base 取不到必须**明确失败**，不许静默放行。

    旧写法没有接住 `git diff` 的退出码 128，于是这道闸在 PR 上的表现是
    "traceback 轰掉 job"——同样是红，但没人能一眼看出原因。
    """
    hook = _load_hook()
    repo, _base = _seed_repo(tmp_path)
    monkeypatch.chdir(repo)

    problem = hook.check_privacy_ci("0000000000000000000000000000000000000000")

    assert problem is not None
    assert "基线" in problem


def test_ci_mode_treats_empty_base_as_missing(tmp_path, monkeypatch, capsys):
    """空串 base 曾等价于「diff 自己跟自己」→ 恒过；现在必须落到实处（走默认值）。"""
    hook = _load_hook()
    repo, _base = _seed_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("JOBWS_PRIVACY_BASE", raising=False)

    assert hook.main(["--privacy-ci", ""]) == 1
    assert "origin/main" in capsys.readouterr().out
