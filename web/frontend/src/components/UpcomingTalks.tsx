import { useTranslation } from "react-i18next";
import type { UpcomingTalkItem } from "../api";
import { EmptyState } from "./ui/empty";

/**
 * 看板的「近 7 天宣讲会」区块（2026-09-18）。
 *
 * 为什么单独一个组件：① `Dashboard.tsx` 是登记过水位的存量文件（只许变小），
 * 区块内联必然超；② 宣讲会数据来自 `talks.csv`、与主表时间线无关，独立组件
 * 让这条边界一眼可见（后端 `_upcoming_talks` 也是独立 helper）。
 *
 * 点任意一条 → 去「准备」板块的宣讲会页签（页签初值走 sessionStorage）。
 */
export function UpcomingTalks({
  items,
  onOpen,
}: {
  items: UpcomingTalkItem[];
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="rounded-lg bg-card-gradient shadow-card ring-1 ring-highlight/5 p-5">
      <h2 className="mb-3 text-sm font-semibold text-foreground">
        {t("dash.upcomingTalks")}
      </h2>
      {items.length === 0 ? (
        <EmptyState title={t("dash.upcomingTalksEmpty")} compact />
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.id}>
              {/* 整行是**真按钮**（独立审查 MINOR）：键盘可 Tab 可达、Enter/Space
                  可触发；看板其他可点列表（待办 / 逾期）也是这个形态——
                  a11y 冒烟不拦这类，但读屏与纯键盘用户会直接撞上。 */}
              <button
                type="button"
                onClick={onOpen}
                className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg bg-secondary/60 px-3 py-2 text-left text-sm transition-colors hover:bg-secondary"
                title={t("dash.viewTalks")}
              >
                <span className="min-w-0 flex-1 truncate text-foreground">
                  {[item.公司, item.形式, item.地点或链接].filter(Boolean).join(" · ")}
                </span>
                <span className="flex shrink-0 items-center gap-2 text-xs">
                  <span className="text-muted-foreground">{item.是否参加}</span>
                  <span className="font-mono text-warning">{item.时间}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
