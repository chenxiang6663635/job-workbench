import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Mail } from "../api";
import { Skeleton } from "./ui/skeleton";

/**
 * 追踪表展开区的「关联邮件」只读块（2026-09-17 收尾批）：批 4.5 方案承诺过的
 * 「投递详情显示关联邮件（只读列表 + 打开按钮）」——后端 `?app=` 过滤与
 * `api.listMails(app)` 早已就绪，这次把前端接上。
 *
 * 边界（与后端同源，不在此处另造口径）：
 * - **只读**：台账的增 / 改 / 删在「进展 → 邮件」里做，这里只服务"回看这条
 *   投递有哪些往来邮件"；不改阶段、不动主表；
 * - 打开原邮件沿用后端随行的 `_openLink`（custom > gmail > none 诚实降级——
 *   none 不给假链接，提示到邮箱里按主题搜）。
 */
export default function RecordMails({ appId }: { appId: string }) {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Mail[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setRows(null);
    setError(null);
    api
      .listMails(appId)
      .then((r) => {
        if (alive) setRows(r.rows);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [appId]);

  if (error) {
    return (
      <p className="text-xs text-destructive">
        {t("app.relatedMailsFailed", { error })}
      </p>
    );
  }
  if (rows === null) {
    return <Skeleton className="h-10 w-full rounded-lg" />;
  }
  if (rows.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">{t("app.relatedMailsEmpty")}</p>
    );
  }
  return (
    <ul className="space-y-1.5">
      {rows.map((m) => (
        <li
          key={m.邮件id}
          className="flex items-center justify-between gap-3 rounded-lg bg-background/60 px-3 py-1.5 text-xs"
        >
          <span className="min-w-0 flex-1 truncate text-foreground" title={m.主题}>
            {m.主题 || "—"}
          </span>
          {/* 日期是日期时间（等宽槽的口径）——与追踪表的日期列一致 */}
          <span className="shrink-0 font-mono text-muted-foreground">
            {(m.日期 || "").split(" ")[0] || "—"}
          </span>
          {m._openLink?.url ? (
            <a
              href={m._openLink.url}
              target="_blank"
              rel="noreferrer"
              title={
                m._openLink.kind === "gmail" ? t("mail.gmailHint") : t("mail.openTitle")
              }
              className="shrink-0 text-primary hover:underline"
            >
              {t("mail.open")}
            </a>
          ) : (
            <span className="shrink-0 text-muted-foreground">
              {t("mail.noLinkHint")}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
