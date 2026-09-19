# -*- coding: utf-8 -*-
"""一次性搬运脚本（PR-B · B-2）：jd_score / report / question_bank 进领域包。

跑完即删。三处改写：
1. 删各文件的 `sys.path.insert` 段（包内不再需要）；
2. 仓内 `import tracker` / `from tracker import` → 包内相对导入；
3. `jd_score.py` 的 `ROOT = dirname(dirname(__file__))` → 注入式 `pathres.resolve_root()`。
   （它的 `PROFILES` 读不到时只警告不失败，搬包后不修就会**静默**缺词典依据。）

Ruling 同 B-1：三个模块不留 shim，直接改新名（引用面 20 处）。
"""
import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parent
SRC = REPO / "tools"
DST = REPO / "packages" / "jobws-core" / "src" / "jobws_core"

SYSPATH_RE = re.compile(
    r"\n_TOOLS_DIR = os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\n"
    r"if _TOOLS_DIR not in sys\.path:\n"
    r"    sys\.path\.insert\(0, _TOOLS_DIR\)\n"
)

report = []
for name in ("jd_score", "report", "question_bank"):
    text = (SRC / (name + ".py")).read_text(encoding="utf-8")
    text, n_path = SYSPATH_RE.subn("\n", text)
    # 仓内 → 包内：tracker 已在同一个包里（PR-A）
    text, n_tr1 = re.subn(r"^(\s*)from tracker import\b", r"\1from .tracker import", text, flags=re.M)
    text, n_tr2 = re.subn(r"^(\s*)import tracker\b", r"\1from . import tracker", text, flags=re.M)
    # workspace_io 同理（真身已在包内）
    text, n_ws = re.subn(
        r"^(\s*)import workspace_io\b", r"\1from jobws_core import workspace_io", text, flags=re.M)
    n_root = 0
    if name == "jd_score":
        text, n_root = re.subn(
            r"^ROOT = os\.path\.dirname\(os\.path\.dirname\(os\.path\.abspath\(__file__\)\)\)$",
            "ROOT = pathres.resolve_root()", text, flags=re.M)
        text = text.replace(
            "import sys\n\n\nROOT = pathres.resolve_root()",
            "import sys\n\nfrom jobws_core import pathres\n\n\nROOT = pathres.resolve_root()",
            1)
    (DST / (name + ".py")).write_text(text, encoding="utf-8")
    report.append("%-18s path段-%d  from-tracker=%d  import-tracker=%d  ws=%d  ROOT=%d"
                  % (name + ".py", n_path, n_tr1, n_tr2, n_ws, n_root))
print("\n".join(report))
