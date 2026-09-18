# -*- coding: utf-8 -*-
"""提示模板（批 8）：四个参数化工作流，与技能（skills/jwb-*）分工不重叠。

边界（调研结论）：prompt **只做参数化组装**——把"要做什么、用哪个技能/命令、
输出什么形态"写成一则可渲染的指令；评分标准、检查清单等准则一律留在技能里
（skills/jwb-jd / jwb-apply / jwb-track），**不在这里复制第二份**（复制就会漂移）。

命名约定：snake_case、不含版本号；参数带说明与默认值；模板自身不读写文件
（写入一律走两段式工具）。

**可得性纪律（2026-09-18 补缺，最重要的一条）**：提示里提到的每条数据，必须是
MCP 面**真拿得到**的。写"读 XX"而实际上拿不到，模型只有两条路——空转或**编造**，
后者正是本项目最忌的结果。因此每个涉及数据的步骤都指到具体资源 URI 或工具调用；
MCP 面没有的能力（如阶段时间线）明说"这边没有，请让用户在界面查看"。
"""

from __future__ import annotations


def _job_name(job_dir):
    """岗位目录名（**不含斜杠**）——模板资源 `jobws://job/{job_name}/...` 要的是它。

    调用方（宿主与用户）常给完整相对路径（如 `01_岗位池/云帆-后端`），而模板变量
    只接受单个目录名。取最后一段，免得宿主拿到一个永远匹配不上的 URI——那种失败
    的表现只是"未知资源"，很容易被当成小事放过。
    """
    return job_dir.replace("\\", "/").rstrip("/").split("/")[-1]


def review_jd(workspace, job_dir=""):
    """评估岗位 JD：资格门槛 → 四维评分 → 投递建议（只读）。"""
    del workspace  # 模板本身不碰数据：数据由宿主按提示去读（resources / 工具）
    if job_dir:
        name = _job_name(job_dir)
        target = ("目标岗位目录：%s\n"
                  "   正文资源：jobws://job/%s/jd（JD 原文）、jobws://job/%s/card（解析卡）"
                  % (job_dir, name, name))
    else:
        target = ("目标未指定：先调 list_jobs（或读资源 jobws://workspace/jobs）让用户选一个岗位")
    return (
        "按求职教练的评分框架评估一个岗位 JD（**只读，不要写任何文件**）。\n"
        "1) %s\n"
        "2) 读该岗位的正文。**资源只给 Markdown 正文**，超长会截断并给出文件路径。\n"
        "   读不到（岗位目录下没有 JD原文.md / 解析卡.md）就是没有——此时请让用户\n"
        "   从界面或工作区文件提供内容，**绝不凭岗位名推断 JD 写了什么**。\n"
        "3) 用技能 jwb-jd 的口径给出：资格门槛判定 → 四维加权评分 → 投递建议\n"
        "输出：结论先行（建议投 / 谨慎 / 不投），再给核心理由与能力缺口。"
        % target
    )


def generate_application_pack(workspace, job_dir=""):
    """生成投递包：按 JD 改简历 → 归档 → 记入追踪表（写入走确认）。"""
    del workspace
    if job_dir:
        name = _job_name(job_dir)
        target = ("目标岗位目录：%s\n"
                  "   需要 JD 内容时读 jobws://job/%s/jd；解析卡在 jobws://job/%s/card"
                  % (job_dir, name, name))
    else:
        target = "目标未指定：先调 list_jobs 让用户选一个岗位"
    return (
        "为指定岗位生成投递包。\n"
        "1) %s\n"
        "2) 读技能 jwb-apply 的流程与技能 jwb-resume 的版式要求\n"
        "3) 产出：按 JD 调整的简历版本 → 归档到岗位目录 → 准备投递记录\n"
        "4) **写入必须走两段式**：preview_add_application / preview_update_application\n"
        "   拿到 token，展示 diff 给用户确认后再调 apply_approval 落盘。\n"
        "5) JD 正文读不到时请让用户提供，**不要自己补写岗位要求**。\n"
        "输出：投递包清单（文件路径）+ 追踪表记录摘要 + 待用户确认的动作。"
        % target
    )


def interview_review(workspace, app_id=""):
    """面试复盘：汇总面试记录 → 提炼要点与改进项（只读）。"""
    del workspace
    target = ("目标记录 id：%s" % app_id) if app_id else \
        "目标未指定：先调 list_applications 让用户选一条记录"
    return (
        "做一次面试复盘（**只读，不要写任何文件**）。\n"
        "1) %s\n"
        "2) 读面试记录：`list_interviews(app_id=\"%s\", verbose=True)`——\n"
        "   **verbose 必须给**，否则拿不到「问题记录 / 我的回答要点 / 复盘与改进」\n"
        "   这三个字段（默认只给轮次 / 形式 / 结果等精简列）。\n"
        "3) **MCP 不提供阶段时间线**（该能力只在界面与命令行有）：需要时间线请让\n"
        "   用户在界面查看，**不要自己拼一条演进过程**。\n"
        "4) 字段为空就写「未填写」，**不要代填**复盘内容。\n"
        "5) 用技能 jwb-track 的口径汇总：表现要点、反复出现的问题、下一步动作。\n"
        "输出：三段式——事实摘要 / 暴露的问题 / 下一次面试前的具体改进项。"
        % (target, app_id or "<记录 id>")
    )


def today_todos(workspace, days=7):
    """今日待办：从看板摘要里挑出今天该做的事（只读）。"""
    del workspace
    return (
        "整理今天的求职待办（**只读，不要写任何文件**）。\n"
        "1) 读看板摘要（资源：jobws://workspace/dashboard），重点看\n"
        "   待办 / 逾期未投 / 静默提醒 三块（窗口 %d 天）\n"
        "2) 需要某条记录的详情时用 list_applications(keyword=..., verbose=True)\n"
        "3) 按紧急度排序（截止日已过的排最前），每条给出：动作 + 对象 + 时限\n"
        "4) 看板里没有的就是没有——**不要补充推测出来的待办**。\n"
        "输出：一份可直接执行的清单（最多 5 条），不要复述无关统计。"
        % int(days)
    )
