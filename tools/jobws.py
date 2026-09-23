# -*- coding: utf-8 -*-
"""求职工作台的**唯一**命令行入口。

为什么合并：`tools/` 下曾有 10 个各自可执行的脚本，文档、CI、技能资产里散着
几十处 `python tools/xxx.py`；一个入口之后，用户只需记住 `jobws`，迁移对照表
见 CHANGELOG 与 Release 说明。

**刻意保留的一件事**：各脚本的 argparse 与 `main()` 都留在原处（**例外**：
与领域模块分离的命令层——`bank` 于 2026-09-18 拆到 `tools/_cli_bank.py`，
`jd` / `resume` 于 2026-09-21 H 批拆到 `tools/_cli_jd_score.py` /
`tools/_cli_resume.py`，对应领域层不再连带 argparse），jobws 只做第一层分发——
把剩余参数**原样转发**给对应模块。这样：

- 参数名、子命令、退出码（0 通过 / 1 业务失败 / 2 用法或配置错误）**一字不改**，
  `tests/test_cli_surface.py` 那张安全网可以平移过来继续钉；
- 后端 `web/backend/` 与 MCP 包照旧 import 这些模块，领域层没动；
- 本批不把 argparse 搬进 jobws——那是「抽领域层」的下一刀，混进这次破坏性
  变更会让 diff 大到没人审得动。

**两条纪律（新增命令时必须守住）**：

1. **选项一律跟在命令之后**。`jobws --workspace X track` 这种写法里，`X` 会被
   当成子命令名而报 invalid choice；写成 `jobws track --workspace X` 才对。
2. **被分发的模块不得在顶层 import 三方库**。`jobws lint pr-title` 跑在
   `pr-title.yml` 这个**不装任何依赖**的 job 上，顶层 import 一旦引入三方库，
   那条分支保护检查会当场挂掉。

用法：

    python tools/jobws.py --help            列出全部命令
    python tools/jobws.py track --help      看 track 的 12 个子命令
    python tools/jobws.py track list --stage 一面
    python tools/jobws.py init --demo
    python tools/jobws.py lint pr-title     校验环境变量 PR_TITLE（CI 用）
    python tools/jobws.py lint size         规模预算（--staged 只扫暂存文件）
    python tools/jobws.py lint legacy-imports   旧名 import 存量（只许下降）
"""

from __future__ import print_function

import argparse
import os
import sys
import warnings

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 注入应用根（CLI 的根 = tools/ 的上一级）。
#
# 这里**用新名**导入、不走旧路径 shim：CLI 是本仓库唯一会真的显示
# DeprecationWarning 的形态（`jobws.py` 就是 `__main__`，其余入口的告警按 Python
# 默认被忽略），而 CLI 契约要求 stderr 干净。
#
# 兜底那一支是给 `jobws lint pr-title` 用的——它跑在**不装任何依赖**的 CI job 上，
# 那时 jobws_core 不可用（与旧路径 shim 的源码形态兜底同款）。
#
# pathres 已不再从 `__file__` 推断根目录：它搬进了 jobws_core，推断值会静默指向
# site-packages 的上层（论证见 tests/test_domain_root.py）。
_REPO_ROOT = os.path.dirname(_TOOLS_DIR)
try:
    from jobws_core import pathres  # noqa: E402
except ImportError:
    _PKG_SRC = os.path.join(_REPO_ROOT, "packages", "jobws-core", "src")
    if os.path.isdir(_PKG_SRC) and _PKG_SRC not in sys.path:
        sys.path.insert(0, _PKG_SRC)
    from jobws_core import pathres  # noqa: E402
pathres.set_app_root(_REPO_ROOT)

import approval  # noqa: E402
import check_domains  # noqa: E402
import check_four_ends  # noqa: E402
import check_i18n_hardcode  # noqa: E402
import check_legacy_imports  # noqa: E402
import check_pr_title  # noqa: E402
import check_size  # noqa: E402
import check_skills  # noqa: E402
import check_themes  # noqa: E402
import check_ui_tokens  # noqa: E402
import init_workspace  # noqa: E402
import install_skills  # noqa: E402
import _cli_bank  # noqa: E402  （题库的命令层；领域层在 question_bank.py，二者 2026-09-18 分离）
import _cli_export  # noqa: E402  （导出：八张 CSV → Obsidian 笔记；只读工作区）
import _cli_jd_score  # noqa: E402  （JD 评分命令层；领域层在 jobws_core.jd_score，二者 2026-09-21 分离）
import prefs  # noqa: E402
import release_assist  # noqa: E402
from jobws_core import report  # noqa: E402
import _cli_resume  # noqa: E402  （简历 PDF 命令层；渲染 / 校验领域函数在 resume_build.py）
# 这里**只能**用旧名：`jobws track` 要的是留仓 CLI 的 `main`（在 `_cli_misc` 里），
# 而包内真身没有它。shim 会发废弃告警，但那条告警对**本入口是误报**——`jobws track`
# 本来就该走它（真正该被劝退的是直跑 `python tools/tracker.py` 的人）。CLI 契约要求
# stderr 干净，所以在这一处显式吞掉；直接跑旧脚本的人仍会看到提示。
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import tracker  # noqa: E402

# (命令, 模块或 None, 一句话说明)。顺序即 --help 的展示顺序。
# 模块为 None 表示这一层还有子命令（见 SUB_TARGETS）。
TARGETS = [
    ("track", tracker, "投递追踪：增删查改、面试/联系人/offer、导入与自检"),
    ("bank", _cli_bank, "题库：list 查、add 加题、update 改题、delete 删题/批量撤回、"
                        "import 从 03_面试准备 导入（写操作走两段式）"),
    ("report", report, "复盘与统计（转化率、停留时长、失败归因）"),
    ("resume", _cli_resume, "按岗位生成投递材料"),
    ("jd", _cli_jd_score, "JD 解析与岗位评分"),
    ("init", init_workspace, "初始化工作区（--demo 铺示例数据）"),
    ("export", _cli_export, "导出工作区（--obsidian：八张 CSV → Obsidian 笔记，每行一笔记）"),
    ("apply", approval, "凭令牌执行已确认的写入（两段式的第二步）"),
    ("prefs", prefs, "工作区偏好（get / set）与环境体检（doctor，含终端字体推荐）"),
    ("release", None, "发版辅助（version 生成当日号 / check 预检与 Release 说明抽取）"),
    ("skills", None, "技能资产（install 分发 / check 校验）"),
    ("lint", None, "检查器（pr-title 标题 / i18n 硬编码 / ui-tokens 界面 token / domains 领域插件 / four-ends 四端一致性 / themes 主题门禁 / size 规模预算 / legacy-imports 旧名存量）"),
]

class _ReleaseVersionTarget(object):
    """`release version` 的薄入口：转给 release_assist.print_next_version。

    为什么单独一个目标对象：同一个模块承载两个子命令时，_dispatch 拼出的 argv
    里**没有子命令名**（`release check` 不带参数也是合法调用），模块无法自行区分。
    """

    __name__ = "release_assist"  # _dispatch 用它拼 sys.argv[0]（诊断显示用）

    @staticmethod
    def main():
        return release_assist.print_next_version()


# (顶层命令, 子命令) -> 模块
SUB_TARGETS = {
    ("skills", "install"): install_skills,
    ("skills", "check"): check_skills,
    ("release", "check"): release_assist,
    ("release", "version"): _ReleaseVersionTarget,
    ("lint", "pr-title"): check_pr_title,
    ("lint", "i18n"): check_i18n_hardcode,
    ("lint", "ui-tokens"): check_ui_tokens,
    ("lint", "domains"): check_domains,
    ("lint", "four-ends"): check_four_ends,
    ("lint", "themes"): check_themes,
    ("lint", "size"): check_size,
    ("lint", "legacy-imports"): check_legacy_imports,
}

SUB_CHOICES = {"skills": ["install", "check"],
               "release": ["check", "version"],
               "lint": ["pr-title", "i18n", "ui-tokens", "domains", "four-ends",
                       "themes", "size", "legacy-imports"]}

HELP_FLAGS = ("-h", "--help")


def build_parser():
    """只解析**到命令这一层**，其余参数留给模块自己（见 main 的说明）。"""
    parser = argparse.ArgumentParser(
        prog="jobws",
        description="求职工作台命令行（唯一入口）",
        epilog="每个命令后面接 --help 看它自己的子命令，例如：jobws track --help")
    subs = parser.add_subparsers(dest="group", metavar="<命令>")

    for name, module, help_text in TARGETS:
        # add_help=False 是必须的：否则 `jobws track --help` 会被这一层吃掉，
        # 打印的是 jobws 自己的说明，用户看不到 track 的 12 个子命令。
        sub = subs.add_parser(name, help=help_text, add_help=False)
        if module is None:
            # nargs="?"：子命令留空时由 main 自己报「缺子命令」并给出可选值。
            # 写成必需的话，`jobws skills --help` 会被 argparse 的缺参错误抢先，
            # 用户反而看不到这一组有哪些子命令。
            sub.add_argument("sub", metavar="<子命令>", nargs="?",
                             help="可选：%s" % " / ".join(SUB_CHOICES[name]))
    return parser


def _dispatch(module, rest):
    """把参数交给模块的 main：参数名与退出码语义由各模块自己负责。

    改 sys.argv 而不是传参：被分发的模块里只有 check_pr_title 的 main 显式接受
    argv，其余都从 sys.argv 解析——统一改 sys.argv 对两边都成立，也不必去
    改它们的签名。
    """
    saved = sys.argv
    sys.argv = [module.__name__] + list(rest)
    try:
        return module.main()
    finally:
        sys.argv = saved


def _exit_code(exc):
    """SystemExit 归一化：None 视为 0，非整数一律 1（`sys.exit("文案")` 就是 1）。"""
    if exc.code is None:
        return 0
    if isinstance(exc.code, int):
        return exc.code
    return 1


def main(argv=None):
    # Windows 控制台默认 GBK；输出被 PowerShell 管道接走（`| Select-Object` 等）
    # 时按 locale 编码，中文会变乱码。与 scripts/review.py、scripts/smoke_backend_exe.py
    # 同款处理：显式改 UTF-8（CI 的 Linux 环境本就是 UTF-8，无行为变化）。
    if sys.stdout is not None and getattr(sys.stdout, "encoding", None):
        if sys.stdout.encoding.lower() != "utf-8":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
            except Exception as exc:  # 只影响显示层、不阻断命令——但要说一声（禁静默吞错）
                print("注意：stdout 切换 UTF-8 失败（%s），中文输出可能乱码" % exc,
                      file=sys.stderr)

    parser = build_parser()
    # parse_known_args 而不是 REMAINDER：subparser 里用 REMAINDER 收集剩余参数时，
    # `--help` 会被当成未识别选项回传到顶层（argparse 的已知组合坑），结果
    # `jobws track --help` 报 unrecognized arguments。改成"认识多少解析多少、
    # 剩下的原样转发"之后，--help 与所有子命令参数都进 rest。
    args, rest = parser.parse_known_args(sys.argv[1:] if argv is None else argv)

    if not getattr(args, "group", None):
        parser.print_help()
        return 1

    sub = getattr(args, "sub", None)
    if sub:
        module = SUB_TARGETS.get((args.group, sub))
        if module is None:
            print("未知子命令：%s %s（可选：%s）"
                  % (args.group, sub, " / ".join(SUB_CHOICES.get(args.group, []))))
            return 2
    else:
        module = None
        for name, mod, _help in TARGETS:
            if name == args.group:
                module = mod
                break
        if module is None:
            # `jobws skills --help` 这种：sub 缺位，但用户只是想看有哪些子命令
            choices = SUB_CHOICES.get(args.group, [])
            if rest and all(item in HELP_FLAGS for item in rest):
                print("用法：jobws %s <%s>" % (args.group, " / ".join(choices)))
                for choice in choices:
                    print("    jobws %s %s" % (args.group, choice))
                return 0
            print("命令缺少子命令：%s（可选：%s）" % (args.group, " / ".join(choices)))
            return 2

    try:
        code = _dispatch(module, rest)
    except SystemExit as exc:
        # argparse 的 --help(0) 与用法错误(2) 都走这里：必须原样透出，
        # 否则 `jobws track --help` 会被误报成失败
        return _exit_code(exc)
    except TimeoutError:
        # 写类操作拿不到 tracker.lock（另一处正在写：桌面端常驻后端 / 另一个命令）。
        # 这不是缺陷、也不是"数据坏了"，用户要的是"再试一次就行"——此前它会直接
        # 抛裸栈（2026-09-23 二轮审查）。Web 侧同一情形已译成 429 server.lockTimeout。
        print("错误：工作区正被另一处写入（等待文件锁超时）——稍后重试；"
              "本次没有写入任何内容。")
        return 1
    return 0 if code is None else code


if __name__ == "__main__":
    sys.exit(main())
