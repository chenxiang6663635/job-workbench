# -*- coding: utf-8 -*-
"""端口身份判据：8765 上跑的是不是本工作台的后端。

从 `main.py` 抽出（2026-10-28）：这个文件已越过规模水位，而这两个函数是
**自包含的纯逻辑**（只依赖 socket / urllib），抽出来零风险。

判据的演进（每一步都被真实问题推着走，别"简化"回去）：

  ① 子串匹配（`b"ok" in r.read()`）—— 任何返回 ok 字样的本地服务都被当成后端；
  ② 结构化 `status == "ok"` —— 严格了，但 `{"status":"ok","service":"unrelated"}`
     仍被接受（2026-10-28 审计的原始反例）；
  ③ 加 `service` —— 当前判据。挡得住陌生服务，挡不住「同一个产品的另一个实例」
     （后者由 Electron 侧的 `instance_id` 处理，见 web/electron/backend_identity.js）。

**两侧判据必须一起改**：Electron 的 `isHealthy` 与这里的 `is_our_service` 是同一条
合同的两种实现，单侧改动会让它们不同源（表现为「桌面端等不到就绪」或「后端误复用」）。
"""


def port_in_use(port):
    """端口是否已有进程监听。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_our_service(port):
    """端口上的服务是否为本工作台的后端：200 + `status=="ok"` + `service=="jobws"`。

    2026-10-28 审计：此前只查 `status`，`{"status":"ok","service":"unrelated"}` 也算
    「我们的」（与 Electron 侧同源的缺陷）。两侧判据必须一起改，各有测试钉住。

    刻意**不**校验数据根：ADR `port-identity` 规定复用的后端用它自己的数据根，
    把数据根做成拒绝条件会让 dev 后端复用失效。
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:%d/api/health" % port, timeout=2
        ) as r:
            payload = json.loads(r.read().decode("utf-8", errors="replace"))
        return (
            isinstance(payload, dict)
            and payload.get("status") == "ok"
            and payload.get("service") == "jobws"
        )
    except Exception:
        return False
