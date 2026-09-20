# -*- coding: utf-8 -*-
"""链接推断（v0.4.0-A 的 A5）：只做能解释的推断，不做半吊子预填。

要钉住的取舍：
1. 已知站点映射（nowcoder / yingjiesheng）与学校域名、企业校招子域的识别；
2. 未知域名**不猜来源**（返回空）——让用户自选强于替他记错一笔；
3. 缺 scheme 的链接补 `https://`；
4. 非 URL 返回 ok=False 而不是抛异常或猜一半。
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "web", "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from jobws_core import url_infer  # noqa: E402


def test_known_job_sites_map_to_sources():
    r = url_infer.infer_from_url("https://www.nowcoder.com/jobs/123")
    assert r["ok"] is True and r["来源"] == "牛客"
    r = url_infer.infer_from_url("https://www.yingjiesheng.com/job-123.html")
    assert r["ok"] is True and r["来源"] == "应届生求职网"


def test_school_and_campus_domains_map_to_sources():
    r = url_infer.infer_from_url("https://job.tsinghua.edu.cn/x")
    assert r["ok"] is True and r["来源"] == "学校就业网"
    r = url_infer.infer_from_url("https://careers.tcl.com/job/1001")
    assert r["ok"] is True and r["来源"] == "企业校招官网"
    r = url_infer.infer_from_url("https://xyzp.example.com/p")
    assert r["ok"] is True and r["来源"] == "企业校招官网"


def test_missing_scheme_is_normalised():
    r = url_infer.infer_from_url("www.nowcoder.com/jobs/123")
    assert r["链接"] == "https://www.nowcoder.com/jobs/123"
    assert r["来源"] == "牛客"


def test_unknown_domain_keeps_link_but_not_source():
    """未知域名：链接照留（它仍是有效 URL），来源留空——不猜「其他」。"""
    r = url_infer.infer_from_url("https://example.com/job/1")
    assert r["ok"] is True
    assert r["链接"] == "https://example.com/job/1"
    assert r["来源"] == ""
    assert any("请手选" in note for note in r["说明"])


def test_non_urls_are_rejected_readably():
    for bad in ("", "   ", "随便一段话", "not a url with spaces"):
        r = url_infer.infer_from_url(bad)
        assert r["ok"] is False, bad
        assert r["链接"] == ""
        assert r["说明"]


def test_infer_never_touches_company_or_role():
    """公司/岗位刻意不推断：说明里必须对用户讲清楚（诚实红线）。"""
    r = url_infer.infer_from_url("https://careers.tcl.com/job/1001")
    assert any("公司与岗位无法从链接可靠推断" in note for note in r["说明"])
    assert "公司" not in r and "岗位" not in r
