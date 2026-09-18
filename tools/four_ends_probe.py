# -*- coding: utf-8 -*-
"""四端探针：读出「实际存在的能力」，供 check_four_ends 与契约比对。

（由 check_four_ends.py 拆出；2026-09-17 批 4.7 的规模预算闸门要求。
只读不写，别处不要再写第二套取值逻辑——判据分叉是这类检查器最容易腐化的地方。）

为什么 MCP 与 GUI 用 `ast` 静态解析而不是 import：它们跑在**独立虚拟环境**
（`mcp/` 有自己的 venv；GUI 依赖 FastAPI / starlette）。import 会把它们的依赖
变成检查器的依赖，还会带来导入副作用——本检查器要能在最朴素的环境里跑：
只读、零依赖、不启服务。
"""

import ast
import io
import json
import os
import re
import sys

_API_CODE_RE = re.compile(r'ApiError\(\s*[^,]+,\s*"([a-z][A-Za-z0-9_]*\.[A-Za-z0-9_]+)"')
_I18N_KEY_RE = re.compile(r'"(err\.[A-Za-z0-9_.]+)"\s*:')


def read(path):
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def cli_capabilities(root):
    """CLI 命令树：直接 import jobws（该模块导入无副作用），读三张命令表。"""
    tools_dir = os.path.join(root, "tools")
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    try:
        import jobws
    except Exception as exc:  # noqa: BLE001 —— 环境缺依赖时给出可读原因
        return None, ["无法 import jobws（%s）" % exc]
    groups = [name for name, _module, _help in jobws.TARGETS]
    subs = {}
    for (group, sub) in jobws.SUB_TARGETS:
        subs.setdefault(group, []).append(sub)
    return {"groups": groups, "subs": subs}, []


def mcp_tools(root):
    """MCP 工具名（按注册顺序）：ast 解析 server.py，抓 @mcp.tool 下的函数名。"""
    path = os.path.join(root, "mcp", "jobws_mcp", "server.py")
    if not os.path.isfile(path):
        return None, ["找不到 mcp/jobws_mcp/server.py"]
    tree = ast.parse(read(path))
    names = []
    for node in ast.walk(tree):
        # 同步与 async 都要认：MCP SDK 与 FastAPI 生态里 async 是主流形态，
        # 漏认会让未来的 async 工具静默消失于探针视野（反向检查也兜不住）。
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            text = ast.unparse(deco) if hasattr(ast, "unparse") else ""
            # 裸 `@mcp.tool`、`@mcp.tool(name=...)`、`@mcp.tool()` 三种都算注册。
            if text == "mcp.tool" or text.startswith("mcp.tool("):
                names.append(node.name)
                break
    return names, []


def _router_prefix(path):
    """从文件里取 `APIRouter(prefix="...")` 的 prefix（没有就返回空串）。"""
    if not os.path.isfile(path):
        return ""
    tree = ast.parse(read(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func_name = getattr(node.value.func, "attr",
                                getattr(node.value.func, "id", ""))
            if func_name != "APIRouter":
                continue
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return ""


def gui_routes(root):
    """GUI 路由：ast 解析 routers/*.py，抓 APIRouter(prefix=...) 与端点装饰器。

    返回 [(method, path)]，path 已含 prefix；方法大写。

    两层结构都要认：`routers/x.py`（自己声明 prefix）与 `routers/<包>/*.py`
    （子模块的 router 通常**不带 prefix**，prefix 在包的 `__init__.py` 上，
    例：`progress/__init__.py` 声明 `/api/progress`）。少认后者，所有
    `/api/progress/*` 的能力都会被误报成"找不到路由"。
    """
    routers_dir = os.path.join(root, "web", "backend", "routers")
    if not os.path.isdir(routers_dir):
        return None, ["找不到 web/backend/routers"]

    targets = []
    for name in sorted(os.listdir(routers_dir)):
        full = os.path.join(routers_dir, name)
        if os.path.isdir(full):
            pkg_prefix = _router_prefix(os.path.join(full, "__init__.py"))
            for sub in sorted(os.listdir(full)):
                if sub.endswith(".py") and sub != "__init__.py":
                    targets.append((os.path.join(full, sub), pkg_prefix))
        elif name.endswith(".py"):
            targets.append((full, ""))

    routes = []
    for path, pkg_prefix in targets:
        tree = ast.parse(read(path))
        prefix = pkg_prefix + _router_prefix(path)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                attr = getattr(deco.func, "attr", "")
                if attr not in ("get", "post", "patch", "put", "delete"):
                    continue
                if not deco.args or not isinstance(deco.args[0], ast.Constant):
                    continue
                routes.append((attr.upper(), prefix + deco.args[0].value))
    return routes, []


def plugin_assets(root):
    """插件命令名（去扩展名）与子代理名：声明文件与目录两边都要读。"""
    declared_cmds, declared_agents = [], []
    path = os.path.join(root, ".codebuddy-plugin", "plugin.json")
    if os.path.isfile(path):
        data = json.loads(read(path))
        declared_cmds = [os.path.basename(item) for item in data.get("commands", [])]
        declared_agents = [os.path.basename(item) for item in data.get("agents", [])]
    commands_dir = os.path.join(root, "commands")
    agents_dir = os.path.join(root, "agents")
    found_cmds = sorted(n for n in os.listdir(commands_dir)
                        if n.endswith(".md")) if os.path.isdir(commands_dir) else []
    found_agents = sorted(n for n in os.listdir(agents_dir)
                          if n.endswith(".md")) if os.path.isdir(agents_dir) else []
    return {
        "commands": [name[:-3] for name in found_cmds],
        "agents": [name[:-3] for name in found_agents],
        "declared_commands": declared_cmds,
        "declared_agents": declared_agents,
    }


def api_codes(root):
    """后端错误码：正则扫 ApiError(status, "域.语义", ...) 的调用点（跳过打包产物）。"""
    codes = set()
    base_root = os.path.join(root, "web", "backend")
    if not os.path.isdir(base_root):
        return codes
    for dirpath, _dirnames, filenames in os.walk(base_root):
        if os.sep + "dist" in dirpath or os.sep + "build" in dirpath:
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            codes.update(_API_CODE_RE.findall(read(os.path.join(dirpath, name))))
    return codes


def i18n_keys(root):
    """中英两份语言包的 err.* 键集合（键必须两侧都在，否则界面会露 key 名）。"""
    locales = os.path.join(root, "web", "frontend", "src", "i18n", "locales")
    result = {}
    for name, tag in (("zh-CN.ts", "zh"), ("en.ts", "en")):
        path = os.path.join(locales, name)
        result[tag] = set(_I18N_KEY_RE.findall(read(path))) if os.path.isfile(path) else set()
    return result
