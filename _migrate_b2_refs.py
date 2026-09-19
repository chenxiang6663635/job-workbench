# -*- coding: utf-8 -*-
"""一次性替换脚本（PR-B · B-2 第二步）：jd_score / report / question_bank 改新名。

跑完即删。引用面 20 处，同 B-1 的 Ruling：不留 shim，一次改完。
"""
import pathlib
import re

FILES = [
    "tools/check_domains.py",
    "tools/jobws.py",
    "tools/approval.py",
    "tools/_cli_bank.py",
    "tools/_cli_export.py",
    "web/backend/routers/dashboard.py",
    "web/backend/routers/jobs.py",
    "web/backend/routers/progress/questions.py",
    "mcp/jobws_mcp/tools_readonly.py",
    "mcp/jobws_mcp/tools_writable.py",
    "mcp/tests/test_tools_batch47.py",
    "tests/test_cli_surface.py",
    "tests/test_dashboard_pool.py",
    "tests/test_questions.py",
    "tests/test_report_clusters.py",
]

RULES = [
    (re.compile(r"^(\s*)from (jd_score|report|question_bank) import\b", re.M),
     r"\1from jobws_core.\2 import"),
    (re.compile(r"^(\s*)import (jd_score|report|question_bank)\b", re.M),
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
    print("%-46s %d" % (rel, hits))
print("合计改写 %d 处" % total)
