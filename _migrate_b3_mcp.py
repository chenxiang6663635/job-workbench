# -*- coding: utf-8 -*-
"""一次性替换脚本（PR-B · B-3）：mcp/tests 改新名 + 删自插 sys.path。

跑完即删。硬闸删掉之后 `tools/` 不再进 sys.path，旧名 import 会直接
ModuleNotFoundError，而且那些 `sys.path.insert(../tools)` 也不再需要。
"""
import pathlib
import re

FILES = [
    "mcp/tests/test_tools.py",
    "mcp/tests/test_tools_writable.py",
    "mcp/tests/test_tools_update.py",
    "mcp/tests/test_tools_batch47.py",
    "mcp/tests/test_resources_prompts.py",
    "mcp/tests/test_stdio_smoke.py",
]

RULES = [
    (re.compile(r"^(\s*)from (tracker|approval|jd_score|report|question_bank) import\b", re.M),
     r"\1from jobws_core.\2 import"),
    (re.compile(r"^(\s*)import (tracker|approval|jd_score|report|question_bank)\b", re.M),
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
    print("%-40s %d" % (rel, hits))
print("合计改写 %d 处" % total)
print("--- 仍含 tools/ sys.path 注入的文件：")
for rel in FILES:
    text = (root / rel).read_text(encoding="utf-8")
    if "../tools" in text or '"tools"' in text:
        print("   ", rel)
