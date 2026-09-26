# -*- coding: utf-8 -*-
"""构建期版本桥：把产品版本真值源写进本包的元数据。

为什么要有 setup.py（而不是纯 pyproject）：版本真值源是
`web/electron/package.json`（月粒度 CalVer，见 docs/contributing.zh-CN.md 的「版本号体系」），而 setuptools 的
`[tool.setuptools.dynamic] version.attr` 只能 **AST 静态读取**字面量、不能执行
`json.load`。构建期仓库一定在侧，故在这里读一次并交给 setuptools。

运行时不读仓库：`jobws/_version.py` 从 `importlib.metadata` 读回本文件写入的值，
读不到则回退占位值（源码未安装 / 元数据被打包剥离）。CI 断言二者与
package.json 三方一致。
"""

import io
import json
import os

import setuptools

_HERE = os.path.dirname(os.path.abspath(__file__))
# packages/jobws-core/ → 仓库根
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_PACKAGE_JSON = os.path.join(_ROOT, "web", "electron", "package.json")


def _product_version():
    with io.open(_PACKAGE_JSON, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version:
        raise RuntimeError(
            "读不到产品版本号：%s 的 version 缺失或不是字符串" % _PACKAGE_JSON
        )
    return version


if __name__ == "__main__":
    setuptools.setup(version=_product_version())
