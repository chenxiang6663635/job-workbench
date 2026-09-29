# -*- coding: utf-8 -*-
"""跨语言页面互链 → 目标语言站点的 URL（MkDocs hook，注册见 site/mkdocs.yml）。

为什么需要：站点文档以 docs/ 为唯一真源，build_site.py 会把「另一语言版本文件」的
链接重写为站点内相对路径（如 zh 手册首行的 English 链接 → `guide.en.md`）。但 i18n
suffix 结构下，每种语言的构建只包含本语言的页面文件：`guide.en.md` 不在 zh 构建里
（`guide.md` 在 en 构建里被解析到 en 变体、指回本页自己）——正文互链会成为坏链
（--strict 红；上线后 zh 站 404 / en 站原地跳）。

本 hook 在 Markdown 渲染前把这类交叉链接换成目标语言的站点 URL：
- 默认语言构建（zh）：`*.en.md` → `/en/<去后缀路径>/`（index 归一为目录层级）
- 非默认语言构建（en）：指向「本页对应的默认语言页」（即 site_path == 本页的
  norm_src_uri，如 en 手册页里的 `guide.md`）的链接 → `/<去后缀路径>/`

只改站内相对 `*.md` 链接（保留锚点）；外链、图片、已是 URL 的链接一律不动。
改写前用 i18n 插件挂好的 alternates 校验「目标语言版本真实存在」；不存在则原样
返回，交给 mkdocs 报 not_found（--strict 拦住）——避免从「严格构建红」退化为
运行时静默 404。

依赖 mkdocs-static-i18n 的内部状态（current_language / default_language /
languages）：该包在 site/requirements.txt 中已 pin，升级时需连同本 hook 一起验证。
"""

import posixpath
import re

_LINK = re.compile(r"(!?\[[^\]]*\]\(\s*)([^()\s]+)((?:[^()]*)\))")
_URL_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _dir_url(clean_path):
    """`manual/guide` → `/manual/guide/`；`privacy/index` → `/privacy/`；`index` → `/`。"""
    if clean_path in ("", ".", "index"):
        return "/"
    if clean_path.endswith("/index"):
        clean_path = clean_path[: -len("/index")]
    return "/" + clean_path + "/"


def _has_locale_version(target_file, locale):
    """目标页的 locale 版本是否真实存在（用 i18n 插件预挂的 alternates 判断）。

    alternates[locale] 只在目标语言版本真实存在时其 .locale == locale；
    仅因 fallback_to_default 补位的回退副本 .locale 仍是默认语言。
    """
    alternate = (getattr(target_file, "alternates", None) or {}).get(locale)
    return alternate is not None and getattr(alternate, "locale", None) == locale


def _rewrite(target, *, src_dir, current, default, non_defaults, page, files):
    path, sep, anchor = target.partition("#")
    if (not path or path.startswith("/") or _URL_SCHEME.match(path)
            or not path.endswith(".md")):
        return target
    site_path = posixpath.normpath(posixpath.join(src_dir, path))
    if site_path.startswith(".."):
        return target

    if current == default:
        for locale in non_defaults:
            suffix = "." + locale + ".md"
            if site_path.endswith(suffix):
                clean = site_path[: -len(suffix)]
                # 目标页的默认语言文件（同页族互链时即 page.file）；改写前先查
                # 它的 alternates，确认另一语言版本真实存在
                target_file = files.src_uris.get(clean + ".md")
                if target_file is None or not _has_locale_version(target_file, locale):
                    return target
                return "/" + locale + _dir_url(clean) + sep + anchor
    elif site_path == getattr(page.file, "norm_src_uri", None):
        if not _has_locale_version(page.file, default):
            return target
        clean = site_path[: -len(".md")]
        return _dir_url(clean) + sep + anchor
    return target


def on_page_markdown(markdown, *, page, config, files):
    i18n = config.plugins.get("i18n")
    if i18n is None or i18n.current_language is None:
        return markdown
    current = i18n.current_language
    default = i18n.default_language
    non_defaults = [lang.locale for lang in i18n.config.languages
                    if not lang.default]
    src_dir = posixpath.dirname(page.file.src_uri)

    def repl(match):
        prefix, target, tail = match.groups()
        new = _rewrite(target, src_dir=src_dir, current=current, default=default,
                       non_defaults=non_defaults, page=page, files=files)
        if new == target:
            return match.group(0)
        return prefix + new + tail

    return _LINK.sub(repl, markdown)
