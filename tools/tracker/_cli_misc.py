# -*- coding: utf-8 -*-
"""CLI 杂项：argparse 组装（按域 helper）与 main 分发。

（由 tools/tracker.py 拆出；2026-09-16 重构批。对外经包门面
re-export，引用方无需改动。）
"""

import argparse
import logging
import os
import re
import sys

_TOOLS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

# 库代码一律走 logging 而不是 print：tracker 被后端常驻进程与 MCP
#（stdout 是协议通道）导入，print 会污染 stdout——logger 存在的理由。
logger = logging.getLogger(__name__)


from . import _core
from ._cli import (cmd_add, cmd_check, cmd_delete, cmd_history, cmd_list, cmd_show, cmd_update)
from ._cli_contact import (cmd_contact)
from ._cli_interview import (cmd_interview)
from ._cli_mail import (cmd_mail)
from ._cli_offer import (cmd_offer)
from ._cli_talk import (cmd_talk)
from ._core import (DEFAULT_WORKSPACE, WORKSPACE)
from ._schema import (BATCHES, INTERVIEW_FORMS, INTERVIEW_RESULTS, INTERVIEW_ROUNDS, MAIL_DIRECTIONS, MAIL_TAGS, SOURCES, TALK_ATTEND, TALK_FORMS)
from .importing import (cmd_import)



def _add_app_parsers(sub):
    """主表（投递记录）的 add / update / list / show / history 子命令。"""
    p_add = sub.add_parser("add", help="新增投递记录")
    p_add.add_argument("--company", required=True, help="公司")
    p_add.add_argument("--role", required=True, help="岗位")
    # 不在 argparse 层写死 choices：合法方向取决于工作区装入的插件，
    # 交给 check_direction() 在运行时校验，才能给出「可用方向」的具体提示
    p_add.add_argument("--direction", required=True, help="方向 ID，取决于装入的领域插件")
    p_add.add_argument("--batch", required=True, choices=BATCHES, help="批次")
    p_add.add_argument("--source", choices=SOURCES, help="来源")
    p_add.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_add.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_add.add_argument("--stage", default="待投", help="当前阶段")
    p_add.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_add.add_argument("--next", dest="next", help="下次动作")
    p_add.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_add.add_argument("--resume", help="简历版本")
    p_add.add_argument("--score", type=int, help="评分 0-100")
    p_add.add_argument("--archive", help="归档目录相对路径")
    p_add.add_argument("--note", help="备注")
    p_add.add_argument("--link", help="岗位页链接（原始 URL，便于日后回看 JD）")
    p_add.add_argument("--preview", action="store_true",
                       help="只预览、并把这次写入登记为一次性令牌（不落盘）；"
                            "确认后用 python tools/jobws.py apply <令牌> 落盘")

    p_upd = sub.add_parser("update", help="更新记录")
    p_upd.add_argument("--id", required=True, help="记录 id，如 A001")
    p_upd.add_argument("--stage", help="当前阶段")
    p_upd.add_argument("--reason", help="状态原因（阶段为已挂/已放弃时必填）")
    p_upd.add_argument("--next", dest="next", help="下次动作")
    p_upd.add_argument("--next-date", dest="next_date", help="下次动作日期 YYYY-MM-DD")
    p_upd.add_argument("--applied", help="投递日期 YYYY-MM-DD")
    p_upd.add_argument("--deadline", help="截止日期 YYYY-MM-DD")
    p_upd.add_argument("--note", help="备注")
    p_upd.add_argument("--score", type=int, help="评分 0-100")
    p_upd.add_argument("--link", help="岗位页链接")
    p_upd.add_argument("--preview", action="store_true",
                       help="只预览、并把这次更新登记为一次性令牌（不落盘）；"
                            "确认后用 python tools/jobws.py apply <令牌> 落盘")

    # 方向选项取决于工作区装入的插件，此处不在定义时写死，
    # 改为在 cmd_list 中校验，以便给出「可用方向」的具体提示
    p_list = sub.add_parser("list", help="列出记录")
    p_list.add_argument("--stage", help="按阶段过滤")
    p_list.add_argument("--direction", help="按方向过滤")
    p_list.add_argument("--batch", choices=BATCHES, help="按批次过滤")
    p_list.add_argument("--company", help="按公司名模糊过滤")
    p_list.add_argument("--due-within", dest="due_within", type=int,
                        help="只看未来 N 天内到期（下次动作日期或截止日期）")

    p_show = sub.add_parser("show", help="查看单条记录")
    p_show.add_argument("--id", required=True, help="记录 id")

    p_hist = sub.add_parser("history", help="查看变更时间线")
    p_hist.add_argument("--id", help="只看某条记录，省略则看全部")
    p_hist.add_argument("--limit", type=int, help="只显示最近 N 条")

    # 2026-09-21 批 D：删除永远两段式——没有 --preview 开关，它是唯一路径
    p_del = sub.add_parser(
        "delete", help="删除投递记录（有关联记录会解绑；预览后凭令牌落盘）")
    p_del.add_argument("--id", required=True, help="记录 id，如 A001")



def _add_interview_parser(sub):
    """面试记录子命令。"""
    p_itv = sub.add_parser("interview", help="面试记录与复盘（add/list/show/update/delete）")
    p_itv.add_argument("action", choices=["add", "list", "show", "update", "delete"])
    p_itv.add_argument("--id", help="面试 id（show/update/delete 必填，如 I001）")
    p_itv.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_itv.add_argument("--company", help="公司（未关联记录时必填）")
    p_itv.add_argument("--role", help="岗位")
    p_itv.add_argument("--round", dest="round", choices=INTERVIEW_ROUNDS,
                       default=None,
                       help="轮次（add 默认一面；update 不传即不改）")
    # 面试时间允许「2026-09-05 14:00」或只有日期，故不套 DATE_RE
    p_itv.add_argument("--when", help="面试时间，如 2026-09-05 14:00")
    p_itv.add_argument("--form", choices=INTERVIEW_FORMS, help="形式")
    p_itv.add_argument("--link", help="会议/作答链接")
    p_itv.add_argument("--interviewer", help="面试官")
    p_itv.add_argument("--questions", help="问题记录")
    p_itv.add_argument("--answers", help="我的回答要点")
    p_itv.add_argument("--retro", help="复盘与改进")
    p_itv.add_argument("--result", choices=INTERVIEW_RESULTS,
                       default=None,
                       help="结果（add 默认待定；update 不传即不改）")
    p_itv.add_argument("--preview", action="store_true",
                       help="只预览、并把这次写入登记为一次性令牌（不落盘）；"
                            "确认后用 python tools/jobws.py apply <令牌> 落盘")



def _add_talk_parser(sub):
    """宣讲会 / 招聘会子命令。"""
    p_talk = sub.add_parser("talk", help="宣讲会 / 招聘会（add/list/show/update/delete）")
    p_talk.add_argument("action", choices=["add", "list", "show", "update", "delete"])
    p_talk.add_argument("--id", help="宣讲会 id（show/update/delete 必填，如 T001）")
    p_talk.add_argument("--company", help="公司（未关联记录时必填）")
    p_talk.add_argument("--when", help="时间，如 2026-09-20 14:00")
    p_talk.add_argument("--form", choices=TALK_FORMS, help="形式")
    p_talk.add_argument("--place", help="地点或链接")
    p_talk.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_talk.add_argument("--attend", choices=TALK_ATTEND, help="是否参加，默认待定")
    p_talk.add_argument("--gain", help="收获（讲了什么、聊到了什么）")
    p_talk.add_argument("--note", help="备注")
    p_talk.add_argument("--preview", action="store_true",
                        help="只预览、并把这次写入登记为一次性令牌（不落盘）；"
                             "确认后用 python tools/jobws.py apply <令牌> 落盘")



def _add_mail_parser(sub):
    """邮件记录子命令。"""
    p_mail = sub.add_parser("mail", help="邮件记录（add/list/show/update/delete）")
    p_mail.add_argument("action", choices=["add", "list", "show", "update", "delete"])
    p_mail.add_argument("--id", help="邮件记录 id（show/update/delete 必填，如 M001）")
    p_mail.add_argument("--message-id", dest="message_id",
                        help="邮件消息 id（Message-ID，可空；有则用于去重与 Gmail 深链）")
    p_mail.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_mail.add_argument("--direction", choices=MAIL_DIRECTIONS, help="方向，默认收")
    p_mail.add_argument("--subject", help="主题（add 必填）")
    p_mail.add_argument("--from", dest="sender", help="发件人")
    p_mail.add_argument("--when", help="日期，如 2026-09-10 10:30")
    p_mail.add_argument("--url", help="原邮件链接（Outlook 等无深链的邮箱可粘贴）")
    p_mail.add_argument("--tag", choices=MAIL_TAGS, help="标签，默认其他")
    p_mail.add_argument("--preview", action="store_true",
                        help="只预览、并把这次写入登记为一次性令牌（不落盘）；"
                             "确认后用 python tools/jobws.py apply <令牌> 落盘")



def _add_contact_parser(sub):
    """联系人子命令。"""
    p_ct = sub.add_parser("contact", help="招聘方联系人（add/list/show/update/delete）")
    p_ct.add_argument("action", choices=["add", "list", "show", "update", "delete"])
    p_ct.add_argument("--id", help="联系人 id（show/update/delete 必填，如 C001）")
    p_ct.add_argument("--app", help="关联的记录 id（如 A001），可省略")
    p_ct.add_argument("--name", help="姓名（add 必填）")
    p_ct.add_argument("--role", help="角色（HR/技术面/猎头…）")
    p_ct.add_argument("--company", help="公司")
    p_ct.add_argument("--contact", help="联系方式")
    p_ct.add_argument("--source", help="来源（BOSS/内推/官网…）")
    p_ct.add_argument("--last", help="最近联系 YYYY-MM-DD")
    p_ct.add_argument("--next-follow", dest="next_follow", help="下次跟进 YYYY-MM-DD")
    p_ct.add_argument("--note", help="备注")



def _add_offer_parser(sub):
    """Offer 子命令。"""
    p_off = sub.add_parser("offer", help="Offer 事实记录（add/list/show/update/delete）")
    p_off.add_argument("action", choices=["add", "list", "show", "update", "delete"])
    p_off.add_argument("--id", help="offer id（show/update/delete 必填，如 O001）")
    p_off.add_argument("--app", help="关联的记录 id，可省略")
    p_off.add_argument("--company", help="公司（未关联记录时必填）")
    p_off.add_argument("--role", help="岗位")
    p_off.add_argument("--salary", help="薪资构成（如 月薪x14 + 年终x2）")
    p_off.add_argument("--monthly", help="月薪")
    p_off.add_argument("--bonus", help="年终")
    p_off.add_argument("--signon", help="签字费")
    p_off.add_argument("--equity", help="股票期权")
    p_off.add_argument("--location", help="工作地点")
    p_off.add_argument("--deadline", help="答复截止日 YYYY-MM-DD")
    p_off.add_argument("--conditions", help="其他条件")
    p_off.add_argument("--note", help="备注")



def _add_misc_parsers(sub):
    """批量导入与 schema 自检子命令。"""
    p_imp = sub.add_parser("import", help="从 CSV 批量导入投递记录")
    p_imp.add_argument("--file", required=True, help="CSV 文件路径（utf-8 / Excel 导出均可）")
    p_imp.add_argument("--dry-run", dest="dry_run", action="store_true",
                       help="只预览校验结果，不写入")
    p_imp.add_argument("--preview", action="store_true",
                       help="预览并把这次导入登记为一次性令牌（不落盘）；"
                            "确认后用 python tools/jobws.py apply <令牌> 落盘")

    sub.add_parser("check", help="schema 自检：列完整性、枚举、外键、坏文件隔离")



def build_parser():
    """组装 argparse 解析器：按域拆成小 helper（各自 ≤80 行）。"""
    parser = argparse.ArgumentParser(description="投递追踪表增删查改")
    parser.add_argument("--workspace", default=DEFAULT_WORKSPACE,
                        help="工作区目录，默认仓库下的 personal/")
    sub = parser.add_subparsers(dest="cmd")
    _add_app_parsers(sub)
    _add_interview_parser(sub)
    _add_talk_parser(sub)
    _add_mail_parser(sub)
    _add_contact_parser(sub)
    _add_offer_parser(sub)
    _add_misc_parsers(sub)
    return parser



def main():
    parser = build_parser()
    args = parser.parse_args()

    _core.WORKSPACE = os.path.abspath(args.workspace)
    if not os.path.isdir(_core.WORKSPACE):
        print("错误：工作区不存在 %s" % _core.WORKSPACE)
        print("先运行 python tools/jobws.py init 初始化。")
        return 1

    if not args.cmd:
        parser.print_help()
        return 1

    handlers = {
        "add": cmd_add,
        "update": cmd_update,
        "list": cmd_list,
        "show": cmd_show,
        "history": cmd_history,
        "delete": cmd_delete,
        "interview": cmd_interview,
        "talk": cmd_talk,
        "mail": cmd_mail,
        "contact": cmd_contact,
        "offer": cmd_offer,
        "import": cmd_import,
        "check": cmd_check,
    }
    return handlers[args.cmd](args)
