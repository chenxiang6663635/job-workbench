# -*- coding: utf-8 -*-
"""邮件文本抽取（批 9 自 `tools/imap_fetch.py` 拆出，原逻辑未改）。

**为什么在领域包**：正文 / ICS 的抽取口径要与解析器（`mail_facts`、`mail_ics`）
同源演进，放在领域层才能被独立安装与测试；`tools/imap_fetch.py` 只保留
IMAP 会话本身，并把这里的名字再导出，既有调用方（后端 / 测试）不受影响。

两条边界：

- **截断只为预览**：`smart_truncate` 按行边界切，并把尾部含链接 / 日期的行
  抢救回来（会议链接常写在正文尾部，硬切会切出半截 URL）；
- **ICS 不截断**：`extract_calendar` 单独取 `text/calendar` 部件原文，交给
  `mail_ics.parse_ics` 按 RFC 5545 读。
"""

import re
from html.parser import HTMLParser

# 单封邮件正文截断上限：列表预览用，防止把超大邮件整个打进响应
MAX_BODY_CHARS = 4000

# 截断时优先保留的「高价值行」：链接与日期
TAIL_KEEP_RE = re.compile(r"https?://|20\d{2}\s*[-/年]|\d{1,2}\s*月\s*\d{1,2}\s*日")
# 尾部最多抢救多少行（一封正文里链接再多，也不该把头部挤没）
MAX_TAIL_LINES = 20


class _HtmlTextExtractor(HTMLParser):
    """尽力而为的 HTML → 纯文本：跳过 script/style，块级标签折算换行。"""

    _BLOCK_TAGS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        HTMLParser.__init__(self)
        self._skip_depth = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self):
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()


def _html_to_text(html_text):
    parser = _HtmlTextExtractor()
    try:
        parser.feed(html_text)
    except Exception:
        # 畸形 HTML 上解析器已尽力；真出错时退回粗剥标签
        return re.sub(r"<[^>]+>", " ", html_text)
    return parser.text()


def _part_text(part):
    """取单个 MIME part 的解码文本；无法解码时返回空串而非抛错。"""
    try:
        payload = part.get_payload(decode=True)
    except Exception:
        payload = None
    if payload is None:
        raw = part.get_payload()
        return raw if isinstance(raw, str) else ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeError):
        return payload.decode("utf-8", errors="replace")


def smart_truncate(text, limit=MAX_BODY_CHARS):
    """按**行边界**截断，并把尾部含链接 / 日期的行抢救回来。

    上限不变（`limit` 个字符，不含尾部标注句）：先从被切掉部分里挑出
    「高价值行」（链接 / 日期，最多占 1/4 预算），再让头部按剩余预算按行切。
    抓不出高价值行时退化为普通按行截断。标注句保留「已截断」字样——既有用例
    与用户都靠它辨认「这不是全文」。
    """
    if len(text) <= limit:
        return text
    head = text[:limit]
    cut = head.rfind("\n")
    if cut > 0:
        head = head[:cut]

    keep, reserved = [], 0
    for line in text[len(head):].splitlines():
        line = line.strip()
        if not line or not TAIL_KEEP_RE.search(line):
            continue
        if len(keep) >= MAX_TAIL_LINES or reserved + len(line) + 1 > limit // 4:
            continue
        keep.append(line)
        reserved += len(line) + 1

    if not keep:
        return head.rstrip() + "\n…（正文过长，已截断）"

    budget = max(1, limit - reserved)
    head = text[:budget]
    cut = head.rfind("\n")
    if cut > 0:
        head = head[:cut]
    return (head.rstrip() + "\n" + "\n".join(keep)
            + "\n…（正文过长，已截断；优先保留含链接与日期的行）")


def extract_body(msg):
    """从 email.message.Message 提取正文纯文本。

    优先 text/plain；只有 HTML 时剥标签；两者都无则返回空串。
    超过 MAX_BODY_CHARS 截断（见 `smart_truncate`）——列表预览不需要全文。
    """
    plain_parts = []
    html_parts = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        # 跳过附件（如 .txt 附件）：它的内容不是邮件正文，混进来会污染解析素材
        disposition = (part.get("Content-Disposition") or "").lower()
        if disposition.startswith("attachment"):
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain":
            plain_parts.append(_part_text(part))
        elif ctype == "text/html":
            html_parts.append(_part_text(part))

    if plain_parts:
        text = "\n".join(p.strip() for p in plain_parts if p.strip())
    elif html_parts:
        text = "\n".join(_html_to_text(h) for h in html_parts if h.strip())
    else:
        text = ""

    return smart_truncate(text.strip())


def extract_calendar(msg):
    """取邮件里 `text/calendar` 部件的原文（会议邀请的结构化真相源）。

    与 `extract_body` 的两点差别：
    1. **不截断**：ICS 本身很短，而时间与会议链接都可能被正文截断切掉；
    2. **不剥标签**：交给解析器（`jobws_core.mail_ics.parse_ics`）按 RFC 5545 读。
    """
    parts = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_content_type() != "text/calendar":
            continue
        text = _part_text(part)
        if text.strip():
            parts.append(text)
    return "\n".join(parts)
