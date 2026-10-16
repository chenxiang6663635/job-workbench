import { useTranslation } from "react-i18next";

import { cn } from "../lib/utils";
import type { NotesOutlineItem } from "../lib/notes";

// 阅读区右栏的「本页大纲」（xl 以上显示）。
//
// 2026-10-16（#274 批）从 NotesReader 原样搬出：那个文件插入「返回上一篇」后越过
// 300 行规模预算，而这一块自成一体（进大纲、出滚动位置），搬出后两边都读得清。
// **纯移动，行为不变**（aria-label / 类名 / 滚动方式都照旧）。
//
// 锚点用 onClick + scrollIntoView，**不能用原生 #hash 跳转**——App 是 hash 路由，
// 未知 hash 会被 tabFromHash 判为无效并跳回看板（不是"跳过去但不动"）。

function jump(id: string): void {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function NotesOutlineNav({ outline }: { outline: NotesOutlineItem[] }) {
  const { t } = useTranslation();
  if (!outline.length) return null;
  return (
    <nav
      className="sticky top-6 hidden w-40 shrink-0 self-start xl:block"
      aria-label={t("notes.outline")}
    >
      <p className="mb-2 text-[0.6875rem] font-medium text-muted-foreground">
        {t("notes.outline")}
      </p>
      <ul>
        {outline.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => jump(item.id)}
              className={cn(
                "block w-full cursor-pointer border-l-2 border-transparent py-0.5 text-left text-xs text-muted-foreground transition-colors hover:border-primary hover:text-foreground",
                item.level === 3 ? "pl-5" : "pl-2.5"
              )}
            >
              {item.text}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
