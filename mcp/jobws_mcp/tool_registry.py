# -*- coding: utf-8 -*-
"""MCP **工具注册表**（2026-10-12 从 server.py 拆出）——只管工具的定义与注册顺序。

为什么单列一个模块：

- `server.py` 原本同时装「服务装配」「工具注册」「资源 / 提示注册」三件事，
  工具越加越长（2026-10-12 时 `build_server()` 已 254 行、文件 378 行）；规模闸
  的函数上限（80 行）此前被 server.py 的文件级豁免一并遮蔽，豁免自洁删除后暴露。
- 注册块没有可抽象的分支，只是顺序铺开的工具定义——按规模闸的指引拆成
  「编排函数 + helper」，并按能力归到本模块（与 `resources` / `prompts` 同款：
  各自模块注册各自原语）。

**顺序纪律（批 4.7，最重要的一条）**：四个 helper 由 `register_all()` **按序调用**，
注册顺序即 `tools/list` 的输出顺序；宿主按前缀比对工具描述做提示缓存，顺序抖动
会让缓存整段失效。`mcp/tests/test_stdio_smoke.py` 钉住了这张清单——**改顺序即红**，
新增工具一律追加在末尾（见最下方 `register_all` 的注释）。

**例外**：`read_job_text` 与岗位正文资源同源，其注册随 `resources.register_text_tool`
在 `server.py` 末尾调用——不进本模块。
"""

import json
from datetime import date

from jobws_core import tracker
# 别名是**必须的**：下方嵌套的工具函数就叫 `score_calibration`，若模块级 import
# 不改名，函数体里查这个名字会命中嵌套函数自己（闭包查找顺序）而不是 core 模块。
from jobws_core import score_calibration as score_calibration_core

from . import annotations, tools_readonly, tools_writable


def _register_application_tools(mcp, workspace):
    """投递记录的只读三件（**顺序组 1**）。"""
    @mcp.tool(annotations=annotations.READ_ONLY)
    def list_applications(stage: str = "", keyword: str = "", limit: int = 20,
                          verbose: bool = False) -> str:
        """列出投递记录（只读）。

        stage 精确匹配当前阶段（如 一面 / offer）；keyword 对公司与岗位做
        子串包含匹配；结果按「下次动作日期」升序、终态沉底排序。
        verbose=True 才给全字段（默认只给精简列——列表类工具要控制体积）。
        """
        data = tools_readonly.list_applications(
            workspace, stage=stage or None, keyword=keyword or None,
            limit=limit, verbose=verbose)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def list_jobs(keyword: str = "", limit: int = 20) -> str:
        """列出岗位池里的岗位（只读）。

        给出公司、岗位、解析卡评分与投递状态（未投递 / 流程中 / 已终态）。
        """
        data = tools_readonly.list_jobs(
            workspace, keyword=keyword or None, limit=limit)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def dashboard_summary() -> str:
        """看板摘要（只读）。

        漏斗分布、近 7 天待办、已过截止仍未投、静默提醒（阶段停留过久）、
        待推进（健康度非正常）、各阶段转化率与失败归因。
        """
        data = tools_readonly.dashboard_summary(workspace)
        return json.dumps(data, ensure_ascii=False, indent=2)


def _register_application_writes(mcp, workspace):
    """投递记录的写入面（**顺序组 2**）：三个预览 + 唯一的落盘入口。"""
    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_add_application(company: str, role: str, direction: str, batch: str,
                                stage: str = "待投", deadline: str = "",
                                applied: str = "", next_action: str = "",
                                next_date: str = "", score: int = -1,
                                source: str = "", resume: str = "",
                                archive: str = "", note: str = "",
                                link: str = "") -> str:
        """预览新增一条投递记录（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        """
        data = tools_writable.preview_add_application(workspace, **{
            "公司": company, "岗位": role, "方向": direction, "批次": batch,
            "当前阶段": stage or "待投", "截止日期": deadline, "投递日期": applied,
            "下次动作": next_action, "下次动作日期": next_date,
            "评分": "" if score is None or score < 0 else str(score),
            "来源": source, "简历版本": resume, "归档目录": archive, "备注": note,
            "链接": link,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_import_applications(csv_text: str) -> str:
        """预览批量导入投递记录（**不写入**）。

        csv_text 是 CSV 全文（含表头）。有错误行时不给令牌——先让用户修数据。
        其余流程同上：展示 diff → 用户确认 → apply_approval。
        """
        data = tools_writable.preview_import_applications(workspace, csv_text)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_update_application(app_id: str, stage: str = "",
                                   next_action: str = "", next_date: str = "",
                                   reason: str = "", score: int = -1,
                                   link: str = "", note: str = "",
                                   applied: str = "", deadline: str = "") -> str:
        """预览更新一条投递记录（**不写入**），返回 token 与逐字段差异表。

        只列**要改**的字段（未传的字段保持原值）；可更新字段与新增同族
        （当前阶段 / 状态原因 / 下次动作 / 下次动作日期 / 备注 / 评分 /
        投递日期 / 截止日期 / 链接）。**先把 diff 展示给用户**，用户确认后
        再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        """
        changes = {}
        for field, value in (("当前阶段", stage), ("状态原因", reason),
                             ("下次动作", next_action), ("下次动作日期", next_date),
                             ("备注", note), ("链接", link),
                             ("投递日期", applied), ("截止日期", deadline)):
            if value:
                changes[field] = value
        if score is not None and score >= 0:
            changes["评分"] = str(score)
        data = tools_writable.preview_update_application(workspace, app_id, changes)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.WRITE_CONFIRMED)  # 唯一写入：非只读、非幂等
    def apply_approval(token: str) -> str:
        """凭令牌执行已确认的写入（两段式的第二步）。

        令牌一次性、默认 10 分钟内有效，且绑定到本服务的工作区——过期、用过、
        或来自别的工作区的令牌都会被拒绝（返回 ok=false 与理由）。
        """
        data = tools_writable.apply_approval(workspace, token)
        return json.dumps(data, ensure_ascii=False, indent=2)


def _register_review_tools(mcp, workspace):
    """面试 / 题库 / JD 评分的只读三件（**顺序组 3**，批 4.7 主线补口）。"""
    @mcp.tool(annotations=annotations.READ_ONLY)
    def list_interviews(app_id: str = "", result: str = "", limit: int = 20,
                        verbose: bool = False) -> str:
        """列出面试记录（只读）。

        app_id 只看关联该投递记录的面试（如 A001）；result 精确匹配结果
        （待定 / 通过 / 未通过 / 取消）；按面试时间倒序，空时间排最后。
        **面试复盘要给 verbose=True**：「问题记录 / 我的回答要点 / 复盘与改进」
        三个字段不在默认精简列里（提示模板 interview_review 依赖它）。
        """
        data = tools_readonly.list_interviews(
            workspace, app_id=app_id or None, result=result or None,
            limit=limit, verbose=verbose)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def score_jd(job_id: str, resume_version: str = "") -> str:
        """读岗位的 JD 解析卡并给出评分与档位（只读）。

        job_id 是岗位池目录名（如 云帆_后端）。解析卡由 AI 或用户写成 Markdown，
        本工具只做**校验与解读**：四个维度之和必须等于总分才给档位（填到一半的
        卡片不给分档）。resume_version 给了才附上差距分析。
        """
        data = tools_readonly.score_jd(workspace, job_id,
                                       resume_version=resume_version or None)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def list_questions(domain: str = "", subject: str = "", status: str = "",
                       keyword: str = "", limit: int = 20,
                       verbose: bool = False) -> str:
        """列出题库题目（只读）。

        按领域 / 科目 / 状态精确筛选；keyword 对题目、答案要点与关联公司岗位做
        子串匹配。筛选口径与命令行 `bank list` 同源。
        verbose=True 才给全字段（默认只给精简列——列表类工具要控制体积）。
        """
        data = tools_readonly.list_questions(
            workspace, domain=domain or None, subject=subject or None,
            status=status or None, keyword=keyword or None, limit=limit,
            verbose=verbose)
        return json.dumps(data, ensure_ascii=False, indent=2)


def _register_review_writes(mcp, workspace):
    """面试 / 题库的写入面（**顺序组 4**）：四个预览，一律两段式。"""
    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_add_interview(app: str = "", company: str = "", role: str = "",
                              round: str = "一面", when: str = "",
                              form: str = "", link: str = "",
                              interviewer: str = "", questions: str = "",
                              answers: str = "", retro: str = "",
                              result: str = "待定") -> str:
        """预览新增一条面试记录（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘；不要跳过展示这一步。
        给了 app（关联记录 id）时，公司与岗位自动从主表带出。
        """
        data = tools_writable.preview_add_interview(workspace, **{
            "关联记录": app, "公司": company, "岗位": role, "轮次": round,
            "面试时间": when, "形式": form, "链接": link,
            "面试官": interviewer, "问题记录": questions,
            "我的回答要点": answers, "复盘与改进": retro, "结果": result,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_update_interview(interview_id: str, result: str = "",
                                 when: str = "", round: str = "",
                                 form: str = "", link: str = "",
                                 interviewer: str = "", questions: str = "",
                                 answers: str = "", retro: str = "") -> str:
        """预览更新一条面试记录（**不写入**），返回 token 与逐字段差异表。

        只改**传了值**的字段（未传的保持原值）；interview_id 形如 I001。
        **先把 diff 展示给用户**，用户确认后再用同一个 token 调 apply_approval。
        """
        changes = {}
        for field, value in (("结果", result), ("面试时间", when), ("轮次", round),
                             ("形式", form), ("链接", link),
                             ("面试官", interviewer), ("问题记录", questions),
                             ("我的回答要点", answers), ("复盘与改进", retro)):
            if value:
                changes[field] = value
        data = tools_writable.preview_update_interview(
            workspace, interview_id, changes)
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_add_question(title: str, domain: str = "", subject: str = "",
                             tags: str = "", difficulty: str = "",
                             answer: str = "", origin: str = "",
                             company: str = "", role: str = "",
                             status: str = "", note: str = "") -> str:
        """预览新增一道题库题目（**不写入**）。

        返回 token 与将要写入的字段（diff）。**先把这个 diff 展示给用户**，
        用户确认后再用同一个 token 调 apply_approval 落盘。
        """
        data = tools_writable.preview_add_question(workspace, **{
            "题目": title, "领域": domain, "科目": subject, "标签": tags,
            "难度": difficulty, "答案要点": answer, "来源": origin,
            "关联公司": company, "关联岗位": role, "状态": status, "备注": note,
        })
        return json.dumps(data, ensure_ascii=False, indent=2)

    @mcp.tool(annotations=annotations.READ_ONLY)
    def preview_import_questions(module_dir: str = "") -> str:
        """预览从 03_面试准备 导入题目（**不写入**）。

        module_dir 是工作区内的相对目录（默认 03_面试准备），越界会被拒绝。
        其余流程同上：展示 diff → 用户确认 → apply_approval 落盘。
        """
        data = tools_writable.preview_import_questions(
            workspace, module_dir=module_dir or None)
        return json.dumps(data, ensure_ascii=False, indent=2)


def register_calibration_tools(mcp, workspace):
    """筛选校准的只读工具（E 批 2026-10-16）——**由 server.py 在末尾调用**。

    为什么不进 `register_all`：协议顺序的真实末尾在 `read_job_text` 之后
    （`resources.register_text_tool` 由 server.py 在 register_all 之后调用），
    塞进 register_all 会把它插到 jobws.info / read_job_text 前面——那正是
    批 4.7 顺序纪律要防的缓存失效。故本函数公开，由 server.py 排在最后。

    只读：不改任何阈值、不写任何配置、不生成投递动作（设计文档 §四 反目标）
    ——因此不需要 `preview_` 前缀。数字全部来自 `jobws_core.score_calibration`
    （领域层唯一实现）：CLI 看板与 API 看板调用的是同一些函数。
    """
    @mcp.tool(annotations=annotations.READ_ONLY)
    def score_calibration() -> str:
        """筛选校准：按评分档位的转化率、未投递记账与一句结论（只读）。

        回答一个问题：*我按评分筛的这一套，测出来的结果支持它吗？*
        分母 = 该档位里**投过**的岗位数（没投的不算，由未投递记账单独回答）；
        样本不足的档位不展示百分比（宁可不说，也不拿噪声当趋势）。
        结论一律「数据显示 + 可能」——本工具不替用户决定放宽阈值。
        """
        rows = tracker.read_rows(workspace)
        data = score_calibration_core.calibration_data(rows, date.today(), workspace)
        return json.dumps(data, ensure_ascii=False, indent=2)


def register_all(mcp, workspace):
    """按**固定顺序**注册全部工具（顺序即 `tools/list` 的输出顺序）。

    新增工具一律**追加在末尾**（在最后一个 helper 里加，或新 helper 排在最后
    调用）——宿主的工具描述缓存按前缀比对，中间插入会让缓存整段失效（批 4.7）。
    真正的协议末尾在 server.py 的 `read_job_text` 之后：晚到的工具走
    `register_calibration_tools`（由 server.py 排在最后调用）。
    """
    _register_application_tools(mcp, workspace)      # 投递只读
    _register_application_writes(mcp, workspace)     # 投递写入（预览 + apply）
    _register_review_tools(mcp, workspace)           # 面试 / 题库 / 评分只读
    _register_review_writes(mcp, workspace)          # 面试 / 题库写入（预览）
