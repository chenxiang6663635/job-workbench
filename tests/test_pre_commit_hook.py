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
