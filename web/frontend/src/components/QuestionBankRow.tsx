import { useTranslation } from "react-i18next";
import type { BankRow } from "../lib/bank";
import { tagsOf, WRONG_TAG } from "../lib/drill";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";

// 状态三态：值就是工作区里的真实取值，不翻译（与 QuestionBank.tsx 顶部的
// 「数据值 → 样式」约定同源）——动它等于给数据改名。
const STATUS_VARIANT: Record<string, "default" | "secondary" | "success"> = {
  未看: "secondary",
  看过: "default",
  会了: "success",
};

/**
 * 题库列表的一行（2026-09-18 从 QuestionBank.tsx 拆出）：整行可点开详情。
 *
 * 为什么整行是 `role="button"` 而不是行内再塞一个真按钮：嵌套交互元素会让
 * 读屏与键盘两套焦点打架；整行当按钮后，Enter / Space 与鼠标走同一条路。
 * 拆成独立文件还有个硬理由：QuestionBank.tsx 是登记过水位的存量文件（只许变小）。
 */
export function QuestionBankRow({ row, onOpen }: { row: BankRow; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <Card
      role="button"
      tabIndex={0}
      aria-label={t("bank.openDetail", { title: row.题目 })}
      onClick={onOpen}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
      className="cursor-pointer p-3 transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background"
    >
      <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[11px]">
        <Badge
          variant={STATUS_VARIANT[row.状态] ?? "secondary"}
          className="rounded px-1.5 py-0.5 text-[11px]"
        >
          {row.状态 || "未看"}
        </Badge>
        {/* 待复习 / 错题（2026-09-21 批次 B-3）：due 来自后端（复用 due_from_rows
            的原因，见 title 悬停）；错题按标签判定（与训练面板 WRONG_TAG 同源） */}
        {row.due && (
          <Badge
            variant="warning"
            className="rounded px-1.5 py-0.5 text-[11px]"
            title={row.reason}
          >
            {t("bank.badgeDue")}
          </Badge>
        )}
        {tagsOf(row.标签 || "").includes(WRONG_TAG) && (
          <Badge variant="destructive" className="rounded px-1.5 py-0.5 text-[11px]">
            {t("bank.badgeWrong")}
          </Badge>
        )}
        {row.领域 && <span className="text-muted-foreground">{row.领域}</span>}
        {row.科目 && <span className="text-muted-foreground">{row.科目}</span>}
        {row.来源 && <span className="text-muted-foreground">{row.来源}</span>}
        {row.关联公司 && (
          <span className="ml-auto text-muted-foreground">
            {row.关联公司}
            {row.关联岗位 ? ` · ${row.关联岗位}` : ""}
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-foreground">{row.题目}</p>
      {row.答案要点 && (
        <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-muted-foreground">
          {row.答案要点}
        </p>
      )}
    </Card>
  );
}
