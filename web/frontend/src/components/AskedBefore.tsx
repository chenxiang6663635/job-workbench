import { useEffect, useState } from "react";
import { BookOpen, MessageSquareQuote, Search, Sparkles, X } from "lucide-react";
import { useTranslation } from "react-i18next";

import { api, type QuestionGroup } from "../api";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input } from "./ui/input";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";

// 「被问过的」视图（2026-09-21 从 QuestionBank.tsx 拆出）：把面试记录里攒下的问题
// 按公司 / 岗位分组回看。拆出的理由是 QuestionBank 是登记过水位的存量文件
// （只许变小），而本次要往「我的题库」加新增入口 / 计数 / 导入差异表——先例同
// QuestionBankRow.tsx（2026-09-18）。

// 轮次用小徽章标出，同一岗位的不同轮次问题一眼能分开。
// 这是「数据值 → 样式」的映射（与 badgeVariants.ts 同类）：key 是工作区里的真实
// 轮次取值，动它等于给数据改名，所以不翻译；只有「没填轮次」这个兜底占位才译。
const ROUND_VARIANT: Record<string, "default" | "secondary" | "success"> = {
  测评: "secondary",
  笔试: "secondary",
  AI面: "default",
  群面: "default",
  一面: "default",
  二面: "default",
  三面: "default",
  HR面: "success",
  终面: "success",
};

function QuestionCard({ item }: { item: QuestionGroup["items"][number] }) {
  const { t } = useTranslation();
  return (
    <Card className="p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px]">
        <Badge
          variant={ROUND_VARIANT[item.轮次] ?? "secondary"}
          className="rounded px-1.5 py-0.5 text-[11px]"
        >
          {item.轮次 || t("question.roundMissing")}
        </Badge>
        {item.面试时间 && <span className="font-mono text-muted-foreground">{item.面试时间}</span>}
        {item.面试官 && <span className="text-muted-foreground">{item.面试官}</span>}
        {item.结果 && item.结果 !== "待定" && (
          <span className={item.结果 === "通过" ? "text-success" : "text-muted-foreground"}>
            {item.结果}
          </span>
        )}
      </div>

      {/* 三段式：问题 → 我的回答要点 → 复盘，与面试详情同一套视觉语言 */}
      <p className="flex gap-2 text-sm leading-relaxed text-foreground">
        <MessageSquareQuote size={14} className="mt-0.5 shrink-0 text-primary" />
        <span>{item.问题记录}</span>
      </p>
      {item.我的回答要点 && (
        <p className="mt-2 pl-6 text-xs leading-relaxed text-muted-foreground">
          <span className="mr-1 text-muted-foreground">{t("question.myAnswer")}</span>
          {item.我的回答要点}
        </p>
      )}
      {item.复盘与改进 && (
        <p className="mt-1.5 rounded-lg border border-warning/20 bg-warning/5 px-2 py-1.5 pl-6 text-xs leading-relaxed text-warning">
          {t("question.retrospective", { value: item.复盘与改进 })}
        </p>
      )}
    </Card>
  );
}

export function AskedBefore() {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<QuestionGroup[]>([]);
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // 输入防抖：题库检索是纯前端过滤不划算（数据在后端 CSV 里），
  // 但也不能每敲一个字就打一次接口
  useEffect(() => {
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      api
        .questionBank(keyword.trim() || undefined)
        .then((r) => {
          setGroups(r.groups);
          setTotal(r.total);
        })
        .catch((e: Error) => setError(e.message))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [keyword]);

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder={t("question.searchPlaceholder")}
          aria-label={t("question.searchPlaceholder")}
          className="pl-9 pr-28"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
          <span className="whitespace-nowrap text-xs text-muted-foreground">
            {loading ? t("question.searching") : t("question.count", { count: total })}
          </span>
          {keyword && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              title={t("common.clear")}
              onClick={() => setKeyword("")}
            >
              <X size={13} />
            </Button>
          )}
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：loading 骨架 / empty 空态 / error 错误条。
          失败时不再同时显示骨架——两张脸同屏比只说失败更糟 */}
      {loading && !error && groups.length === 0 ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-24 w-full rounded-lg" />
          ))}
        </div>
      ) : !loading && !error && groups.length === 0 ? (
        <Card className="border-dashed">
          <EmptyState
            icon={<BookOpen size={20} />}
            title={keyword ? t("question.emptyNoMatch") : t("question.emptyNoData")}
            description={
              keyword ? t("question.emptyHintNoMatch") : t("question.emptyHintNoData")
            }
          />
        </Card>
      ) : groups.length === 0 ? null : (
        <div className="flex flex-1 flex-col gap-4">
          {groups.map((g) => (
            <Card key={`${g.公司}__${g.岗位}`} className="rounded-lg p-4">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={14} className="text-primary" />
                <span className="text-sm font-semibold text-foreground">{g.公司}</span>
                {g.岗位 && <span className="text-xs text-muted-foreground">{g.岗位}</span>}
                <Badge variant="secondary" className="ml-auto text-[11px]">
                  {t("question.groupCount", { count: g.total })}
                </Badge>
              </div>
              <div className="space-y-2">
                {g.items.map((item) => (
                  <QuestionCard key={item.id || item.问题记录} item={item} />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
