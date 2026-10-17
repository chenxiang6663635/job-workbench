# -*- coding: utf-8 -*-
""S4 负向探针：故意失败，验证 Required Checks 真的阻断合并（用完即删）。""


def test_required_check_blocks_merge():
    assert False, ""S4 negative probe: this PR must NOT be mergeable""
