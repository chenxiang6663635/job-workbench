import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { GitBranch } from "lucide-react";
import { api, type LineageItem } from "../api";
import { Badge } from "./ui/badge";
import { Card } from "./ui/card";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";

/** 阶段 → Badge 语义色：终态=中性、offer/签约=成功、其余进行中=主色 */
function stageBadgeVariant(stage: string) {
  if (stage === "offer" || stage === "签约") return "success" as const;
  if (stage === "已挂" || stage === "已放弃") return "secondary" as const;
  return "default" as const;
}

/**
 * 版本谱系：每个简历版本投了哪些岗位、各处于什么阶段。
 * 数据来自 tracker.csv 的「简历版本」列，纯只读聚合——
 * 回答"这版简历到底投给了谁"，派生关系一目了然。
 */
export default function VersionLineage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<LineageItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    api
      .lineage()
      .then((r) => {
        setItems(r.items);
        setLoaded(true);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const head = (
    <div className="flex items-center gap-2">
      <GitBranch size={15} className="text-primary" />
      <h3 className="text-sm font-medium text-foreground">{t("lineage.title")}</h3>
      <span className="text-[11px] text-muted-foreground">
        {t("lineage.subtitle")}
      </span>
    </div>
  );

  // 三态：失败不再静默消失（此前 error 直接 return null，用户无从察觉）
  if (error) {
    return (
      <div className="space-y-3">
        {head}
        <ErrorBanner message={t("lineage.loadFailed", { error })} />
      </div>
    );
  }

  if (!loaded) {
    return (
      <div className="space-y-3">
        {head}
        <div className="grid gap-3 lg:grid-cols-2">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-28 w-full" />
        </div>
      </div>
    );
  }

  if (items.length === 0) return null;

  return (
    <div className="space-y-3">
      {head}

      <div className="grid gap-3 lg:grid-cols-2">
        {items.map((it) => (
          <Card key={it.version} className="p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium text-foreground">{it.version}</p>
              <span className="text-[11px] text-muted-foreground">
                {t("lineage.jobCount", { count: it.total })}
              </span>
            </div>
            <div className="mt-2.5 space-y-1.5">
              {it.applications.map((a) => (
                <div key={a.id} className="flex items-center gap-2 text-xs">
                  <span className="w-11 shrink-0 text-muted-foreground">{a.id}</span>
                  <span className="flex-1 truncate text-foreground">
                    {a.公司} {a.岗位}
                  </span>
                  {a.投递日期 && (
                    <span className="shrink-0 text-muted-foreground">{a.投递日期}</span>
                  )}
                  <Badge variant={stageBadgeVariant(a.当前阶段)} className="shrink-0">
                    {a.当前阶段 || "—"}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

      {items.some((i) => i.version === "（未填版本）") && (
        <p className="text-[11px] text-muted-foreground">
          {t("lineage.tip")}
        </p>
      )}
    </div>
  );
}
