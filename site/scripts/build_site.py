# -*- coding: utf-8 -*-
"""站点组装器：按白名单把 docs/ 公开文档组装进 MkDocs 的 docs_dir。

为什么白名单是**正列**：docs/ 会持续新增内部文档（研究 / 决策 / 规格），站点是公开面——
漏一个文件就是隐私事故。所以这里只列"允许进产物"的路径，其余一概不复制
（边界由 tests/test_build_site.py 的产物清单断言钉住）。

用法（site.yml 里由 CI 依次调用）：
    python site/scripts/build_site.py
    python -m mkdocs build -f site/mkdocs.yml --strict

链接重写（只作用于从 docs/ 复制进来的文档；站点新写的模板页自己写站点链接）：
1. 指向白名单内文档 → 相对当前输出页的站点路径（如 manual/guide.md 里的
   `../privacy/index.md`；MkDocs 按"相对当前页"解析，跨目录必须带 ../，
   否则 --strict 会因坏链失败）；
2. 其余相对 `*.md` 链接（含 `../README.md` 等仓库文件）→ GitHub 仓库链接；
3. `docs/screenshots/` 下的图片 → `assets/screenshots/`（保子目录）；
4. 外链、锚点、其它一律不动。
"""

import argparse
import json
import posixpath
import re
import shutil
import sys
from pathlib import Path

GITHUB_BLOB = "https://github.com/chenxiang6663635/job-workbench/blob/main/"

# 仓库相对路径 → 站点内路径（正列白名单；Task 2-6 依赖这张表）
DOC_PAGES = {
    "docs/usage-guide.zh-CN.md": "manual/guide.md",
    "docs/usage-guide.md": "manual/guide.en.md",
    "docs/data-flow-matrix.md": "privacy/index.md",
    "docs/support-and-compatibility.md": "compat/index.md",
}
SCREENSHOTS_SRC = "docs/screenshots/"
SCREENSHOTS_DST = "assets/screenshots/"
TEMPLATE_DIR = "site/content"
TEMPLATE_SUFFIX = ".tmpl.md"

_HEADING_DATE = re.compile(r"^## \[[^\]]+\] - (\d{4}-\d{2}-\d{2})", re.MULTILINE)
_LINK = re.compile(r"(!?\[[^\]]*\])\(\s*([^()\s]+)((?:[^()]*)\))")
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def parse_version(package_json_text):
    """web/electron/package.json 的 version——版本号的唯一来源。"""
    return json.loads(package_json_text.lstrip("\ufeff"))["version"]


def parse_release_date(changelog_text):
    """CHANGELOG 里第一个带日期的版本段（`## [x.y.z] - YYYY-MM-DD`）的日期。

    没有日期段时回退空串——「bump 后、落章前」是发布窗口里的正常中间态，
    不该让组装失败；模板会把空串原样渲染。
    """
    match = _HEADING_DATE.search(changelog_text)
    return match.group(1) if match else ""


def render_template(text, *, version, release_date):
    """替换 `{{VERSION}}` / `{{RELEASE_DATE}}`（未列出的占位符保留原样）。"""
    return text.replace("{{VERSION}}", version).replace(
        "{{RELEASE_DATE}}", release_date)


def _output_path(source):
    """源文件（仓库相对路径）→ 输出站点路径；不在白名单映射内则报错。"""
    if source not in DOC_PAGES:
        raise ValueError("source 不在白名单映射内：%s" % source)
    return DOC_PAGES[source]


def _relative(target, out_path):
    """目标站点路径 → 相对当前输出页的相对链接（MkDocs 的解析基准）。"""
    return posixpath.relpath(target, posixpath.dirname(out_path) or ".")


def _rewrite_target(target, source, out_path):
    path, sep, anchor = target.partition("#")
    if not path or path.startswith("/") or _URL_SCHEME.match(path):
        return target
    repo_path = posixpath.normpath(
        posixpath.join(posixpath.dirname(source), path))
    if repo_path in DOC_PAGES:
        return _relative(DOC_PAGES[repo_path], out_path) + sep + anchor
    if repo_path.startswith(SCREENSHOTS_SRC) and repo_path.endswith(".png"):
        shots = SCREENSHOTS_DST + repo_path[len(SCREENSHOTS_SRC):]
        return _relative(shots, out_path) + sep + anchor
    if repo_path.endswith(".md") and not repo_path.startswith(".."):
        return GITHUB_BLOB + repo_path + sep + anchor
    # 落到仓库之外的相对链接（../.. 越界）不动——拼成 GitHub 链接只会是坏链
    return target


def rewrite_links(text, *, source):
    """按四规则重写 md 链接（source = 源文件在仓库中的相对路径）。"""
    out_path = _output_path(source)

    def repl(match):
        label, target, tail = match.groups()
        return "%s(%s%s" % (label, _rewrite_target(target, source, out_path), tail)

    return _LINK.sub(repl, text)


def _read_text(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return fh.read()


def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def assemble(repo_root, out_dir):
    """组装产物；out_dir 清空重建（产物 = 本次白名单内容的纯净函数）。

    拒绝把 out_dir 指到仓库根或仓库根之上——本函数会删除 out_dir，
    那个方向指错了没有任何恢复手段。
    """
    repo_root = Path(repo_root)
    out_dir = Path(out_dir)
    out_res, repo_res = out_dir.resolve(), repo_root.resolve()
    if out_res == repo_res or out_res in repo_res.parents:
        raise ValueError("拒绝把输出目录指到仓库根或仓库根之上：%s" % out_dir)

    version = parse_version(
        _read_text(repo_root / "web" / "electron" / "package.json"))
    release_date = parse_release_date(_read_text(repo_root / "CHANGELOG.md"))

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for src_rel, dst_rel in DOC_PAGES.items():
        _write_text(out_dir / dst_rel,
                    rewrite_links(_read_text(repo_root / src_rel), source=src_rel))

    n_templates = 0
    content = repo_root / TEMPLATE_DIR
    if content.is_dir():
        for path in sorted(content.rglob("*" + TEMPLATE_SUFFIX)):
            rel = path.relative_to(content).as_posix()
            text = render_template(_read_text(path),
                                   version=version, release_date=release_date)
            out_rel = rel[:-len(TEMPLATE_SUFFIX)] + ".md"
            _write_text(out_dir / out_rel, text)
            n_templates += 1

    n_shots = 0
    shots = repo_root / SCREENSHOTS_SRC
    for pattern in ("*.png", "zh-CN/*.png"):
        for path in sorted(shots.glob(pattern)):
            rel = path.relative_to(shots).as_posix()
            dst = out_dir / SCREENSHOTS_DST / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dst)
            n_shots += 1

    print("assemble: %d docs + %d templates + %d screenshots -> %s"
          % (len(DOC_PAGES), n_templates, n_shots, out_dir))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="build_site",
        description="按白名单把 docs/ 公开文档组装进 MkDocs 的 docs_dir")
    parser.add_argument("--repo-root", default=None,
                        help="仓库根（默认：本脚本所在仓库）")
    parser.add_argument("--out", default=None,
                        help="输出目录（默认：<repo>/site/.build/docs）")
    args = parser.parse_args(argv)
    repo_root = (Path(args.repo_root) if args.repo_root
                 else Path(__file__).resolve().parents[2])
    out_dir = (Path(args.out) if args.out
               else repo_root / "site" / ".build" / "docs")
    assemble(repo_root, out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
