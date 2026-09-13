# -*- coding: utf-8 -*-
"""后端 error_code 的 params 与前端文案的 {{占位符}} 必须对得上。

这是 ③（后端 error_code + 前端映射）最容易漂的地方：后端改了参数名、或前端
改了文案里的插值名，**两边都不会报错**，只是界面上直接显示 `{{stage}}` 这串
花括号——功能不坏、但那一句文案就废了，而且只有真正触发那个错误的人才会看到。

核四件事（都是"两侧各自合法、合起来才错"的类型）：
  1. 每个 code 在前端都有 `err.<code>` key；
  2. 文案里出现的每个 {{name}}，后端必须传同名参数；
  3. 同一个 code 在多处抛出时，参数集合一致（否则其中一处文案缺值）；
  4. zh 与 en 的占位符集合一致（翻译时漏掉一个插值）。

后端用 ast 解析（不靠正则猜跨行 kwargs），前端读语言包源码。
"""

import ast
import io
import os
import re
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT_DIR, "web", "backend")
LOCALES = os.path.join(ROOT_DIR, "web", "frontend", "src", "i18n", "locales")


def _backend_calls():
    """返回 {code: [(参数集合, 位置), ...]}。"""
    calls = {}
    for dirpath, dirnames, filenames in os.walk(BACKEND):
        dirnames[:] = [d for d in dirnames if d not in ("build", "dist", "__pycache__")]
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            with io.open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # 裸名 `ApiError(...)` 与属性调用 `apierror.ApiError(...)` 都要认——
                # 只认裸名的话，换个写法就能让新错误悄悄绕过这套断言
                named = ((isinstance(func, ast.Name) and func.id == "ApiError")
                         or (isinstance(func, ast.Attribute) and func.attr == "ApiError"))
                if not named:
                    continue
                if len(node.args) < 2 or not isinstance(node.args[1], ast.Constant):
                    continue
                keys = frozenset(kw.arg for kw in node.keywords if kw.arg)
                rel = os.path.relpath(path, ROOT_DIR).replace(os.sep, "/")
                calls.setdefault(node.args[1].value, []).append(
                    (keys, "%s:%d" % (rel, node.lineno)))
    return calls


def _locale_keys(lang):
    """返回 {key: {占位符}}。"""
    with io.open(os.path.join(LOCALES, "%s.ts" % lang), "r", encoding="utf-8") as f:
        src = f.read()
    out = {}
    for m in re.finditer(r'"(err\.[^"]+)":\s*"((?:[^"\\]|\\.)*)"', src):
        out[m.group(1)] = set(re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", m.group(2)))
    return out


def test_every_code_has_keys_in_both_languages():
    calls = _backend_calls()
    assert calls, "没扫到任何 ApiError——检查是不是改名了"
    zh, en = _locale_keys("zh-CN"), _locale_keys("en")
    missing = ["err." + c for c in calls
               if ("err." + c) not in zh or ("err." + c) not in en]
    assert missing == [], "这些 code 缺前端语言包 key：%s" % missing


def test_placeholder_names_match_backend_params():
    calls = _backend_calls()
    zh = _locale_keys("zh-CN")
    problems = []
    for code in sorted(calls):
        want = zh.get("err." + code)
        if want is None:
            # 不能 continue：缺 key 时这条断言会静默空转（另有 test 1 兜底，
            # 但这里也报出来，缺 key 与参数不匹配是两种修改路径）
            problems.append("err.%s 缺语言包 key（%s 的文案要）"
                            % (code, calls[code][0][1]))
            continue
        for keys, where in calls[code]:
            missing = want - keys
            if missing:
                problems.append("%s 没传 %s（%s 的文案要）"
                                % (where, sorted(missing), "err." + code))
    assert problems == [], "\n".join(problems)


def test_same_code_passes_the_same_params_everywhere():
    """同一语义在两处抛出时参数必须一致，否则其中一处文案缺值。"""
    problems = []
    for code, entries in sorted(_backend_calls().items()):
        sets = {e[0] for e in entries}
        if len(sets) > 1:
            problems.append("%s 多处调用参数不一致：%s" % (code, [sorted(s) for s in sets]))
    assert problems == [], "\n".join(problems)


def test_placeholders_match_between_languages():
    zh, en = _locale_keys("zh-CN"), _locale_keys("en")
    problems = [k for k in sorted(set(zh) & set(en)) if zh[k] != en[k]]
    assert problems == [], "中英文占位符不一致：%s" % problems
