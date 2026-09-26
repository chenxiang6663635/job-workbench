import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, CalendarClock, Clock, Megaphone } from "lucide-react";
import { fetchReminders } from "../lib/reminders";
import { reminderLines, type ReminderLine } from "../lib/reminderMeta";
import type { RemindersDue } from "../lib/domainTypes";

/** 行图标（纯 UI 映射；显示判定都在 lib 的 reminderLines 里，可单测）。 */
const LINE_ICON: Record<ReminderLine["kind"], typeof Clock> = {
  overdue: AlertTriangle,
  todos: Clock,
  talks: Megaphone,
};

/**
 * 内容区顶部的常驻提醒条（首发前收口批 笔 5 的前端半件）。
 *
 * 与系统通知的分工：通知在**没看 app 时**每天戳一次（主进程定时拉同一端点）；
 * 这条在**已经打开** app 时把"今天有什么"摆在最上面——不必记得去翻看板。
 *
 * 三条纪律：
 * - 无到点事项时整条不渲染（判定见 lib/reminders.ts 的 reminderLines，有单测）；
 * - 跳转用 hash 路由（App 的 hashchange 监听会切 tab）——零耦合，不 import App 的 switchTab；
 * - 拉取失败只 console.error 并整条不出：提醒条是锦上添花，不该在任何页面上报错打扰
 *   （数据层错误已由各页自己的通道报 —— 见 Settings 的 ErrorBanner）。
 *
 * `role="status"` 与全站 LiveRegion 的分工：LiveRegion 是**操作反馈**队列（点了按钮的
 * 成功播报），这是**常驻信息**区（打开时若有到点事项，屏幕阅读器顺口报一句）。
 */
export default function ReminderBar() {
  const { t } = useTranslation();
  const [due, setDue] = useState<RemindersDue | null>(null);

  useEffect(() => {
    let alive = true;
    fetchReminders()
      .then((d) => {
        if (alive) setDue(d);
      })
      .catch((e: unknown) => {
        // 控制台日志不是界面文案：保持英文，免得被「残余硬编码」检查误伤
        console.error("fetchReminders failed", e);
      });
    return () => {
      alive = false;
    };
  }, []);

  const lines = reminderLines(due);
  if (lines.length === 0) return null;

  // 逾期 = 真误事了：整条转 destructive；只剩待办/宣讲会时是 warning（提醒，不是警报）
  const hasAlert = lines.some((line) => line.severity === "alert");

  // 链接文字不用 warning/destructive 色（深底上小字对比度不足，见 applicationMeta 的实测），
  // 颜色只落在图标与边框上，文字保持 foreground。
  const linkCls = "flex items-center gap-1 text-foreground underline-offset-2 hover:underline";

  return (
    <div
      role="status"
      className={`mb-6 flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border px-4 py-2 text-xs ${
        hasAlert
          ? "border-destructive/30 bg-destructive/10"
          : "border-warning/30 bg-warning/10"
      }`}
    >
      <span className="flex items-center gap-1.5 font-medium text-foreground">
        <CalendarClock size={14} className={hasAlert ? "text-destructive" : "text-warning"} />
        {t("reminder.title")}
      </span>

      {lines.map((line) => {
        const Icon = LINE_ICON[line.kind];
        return (
          <a key={line.kind} href={line.href} className={linkCls}>
            <Icon
              size={13}
              className={line.severity === "alert" ? "text-destructive" : "text-warning"}
            />
            {t(line.labelKey, { count: line.count, days: due?.window })}
          </a>
        );
      })}
    </div>
  );
}
