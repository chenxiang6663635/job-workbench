# -*- coding: utf-8 -*-
"""旧入口兼容层：投递追踪已包化为 `tools/tracker/`（2026-09-16 重构批）。

此文件**不承载任何业务**，只保留「直跑迁移提示」——与其它旧脚本同一口径：
不保留旧别名，但也不让人对着静默退出发愣。`import tracker` 解析到的是
**包**（Python 语义：同名包优先于模块），41 个引用点无需改动。
"""

import sys

if __name__ == "__main__":
    print("该脚本已包化为 tools/tracker/，请改用：python tools/jobws.py track ...")
    print("查看全部命令：python tools/jobws.py --help")
    sys.exit(2)
