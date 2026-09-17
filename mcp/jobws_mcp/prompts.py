# -*- coding: utf-8 -*-
"""提示模板（批 8）：四个参数化工作流，与技能（skills/jwb-*）分工不重叠。

边界（调研结论）：prompt **只做参数化组装**——把"要做什么、用哪个技能/命令、
输出什么形态"写成一则可渲染的指令；评分标准、检查清单等准则一律留在技能里
（skills/jwb-jd / jwb-apply / jwb-track），**不在这里复制第二份**（复制就会漂移）。

命名约定：snake_case、不含版本号；参数带说明与默认值；模板自身不读写文件
（写入一律走两段式工具）。
"""

from __future__ import annotations


def review_jd(workspace, job_dir=""):
    """评估岗位 JD：资格门槛 → 四维评分 → 投递建议（只读）。"""
    del workspace  # 模板本身不碰数据：数据由宿主按提示去读（resources / 工具）
    target = ("目标岗位目录：%s" % job_dir) if job_dir else \
        "目标未指定：先调 list_jobs（或读资源 jobws://workspace/jobs）让用户选一个岗位"
    return (
        "按求职教练的评分框架评估一个岗位 JD（**只读，不要写任何文件**）。\n"
        "1) %s\n"
        "2) 读该岗位的 JD 原文与解析卡（资源：jobws://workspace/jobs）\n"
        "3) 用技能 jwb-jd 的口径给出：资格门槛判定 → 四维加权评分 → 投递建议\n"
        "输出：结论先行（建议投 / 谨慎 / 不投），再给核心理由与能力缺口。"
        % target
    )


def generate_application_pack(workspace, job_dir=""):
    """生成投递包：按 JD 改简历 → 归档 → 记入追踪表（写入走确认）。"""
    del workspace
    target = ("目标岗位目录：%s" % job_dir) if job_dir else \
        "目标未指定：先调 list_jobs 让用户选一个岗位"
    return (
        "为指定岗位生成投递包。\n"
        "1) %s\n"
        "2) 读技能 jwb-apply 的流程与技能 jwb-resume 的版式要求\n"
        "3) 产出：按 JD 调整的简历版本 → 归档到岗位目录 → 准备投递记录\n"
        "4) **写入必须走两段式**：preview_add_application / preview_update_application\n"
        "   拿到 token，展示 diff 给用户确认后再调 apply_approval 落盘。\n"
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
        "2) 读该记录的面试记录（轮次 / 形式 / 问题 / 自评）与阶段时间线\n"
        "3) 用技能 jwb-track 的口径汇总：表现要点、反复出现的问题、下一步动作\n"
        "输出：三段式——事实摘要 / 暴露的问题 / 下一次面试前的具体改进项。"
        % target
    )


def today_todos(workspace, days=7):
    """今日待办：从看板摘要里挑出今天该做的事（只读）。"""
    del workspace
    return (
        "整理今天的求职待办（**只读，不要写任何文件**）。\n"
        "1) 读看板摘要（资源：jobws://workspace/dashboard），重点看\n"
        "   待办 / 逾期未投 / 静默提醒 三块（窗口 %d 天）\n"
        "2) 按紧急度排序（截止日已过的排最前），每条给出：动作 + 对象 + 时限\n"
        "输出：一份可直接执行的清单（最多 5 条），不要复述无关统计。"
        % int(days)
    )
