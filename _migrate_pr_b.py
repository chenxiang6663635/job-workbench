# -*- coding: utf-8 -*-
"""一次性替换脚本（PR-B）：url_infer / tls_policy / status_parse 三个旧名改新名。

跑完即删。Ruling 依据（见 .superpowers/sdd/批6第二批/progress.md）：这三个模块的
引用面只有 11 处，比 tracker(49)/approval(26) 小一个量级——不留 shim，一次改完，
水位直接到 0。
"""
import pathlib
import re

FILES = [
    "web/backend/routers/applications.py",   # status_parse + url_infer
    "web/backend/routers/imap.py",           # tls_policy
    "web/backend/tls_http.py",               # tls_policy
    "tools/imap_fetch.py",                   # tls_policy
    "tests/test_status_parse.py",
    "tests/test_tracker_schema.py",
    "tests/test_tls_http.py",
    "tests/test_tls_policy.py",
    "tests/test_tls_wiring.py",
    "tests/test_url_infer.py",
]

RULES = [
    (re.compile(r"^(\s*)from (url_infer|tls_policy|status_parse) import\b", re.M),
     r"\1from jobws_core.\2 import"),
    (re.compile(r"^(\s*)import (url_infer|tls_policy|status_parse)\b", re.M),
     r"\1from jobws_core import \2"),
]

root = pathlib.Path(__file__).resolve().parent
total = 0
for rel in FILES:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    hits = 0
    for pattern, repl in RULES:
        text, n = pattern.subn(repl, text)
        hits += n
    if hits:
        path.write_text(text, encoding="utf-8")
    total += hits
    print("%-42s %d" % (rel, hits))
print("合计改写 %d 处" % total)
