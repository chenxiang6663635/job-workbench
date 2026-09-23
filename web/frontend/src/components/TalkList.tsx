import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Megaphone, Plus } from "lucide-react";
import DeleteRecordButton from "./DeleteRecordButton";
import { previewDeleteRecord } from "../lib/records";
import { useSeq } from "../hooks/useSeq";
import { api, TALK_ATTEND, type Talk } from "../api";
import { domainLabel } from "../lib/domainLabels";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { EmptyState } from "./ui/empty";
import { Skeleton } from "./ui/skeleton";
import { ErrorBanner } from "./ErrorBanner";
import TalkForm from "./TalkForm";

/** 表单草稿（`link` = 关联的投递记录 id；「地点或链接」是活动地址，与它无关）。 */


export default function TalkList() {
  const { t } = useTranslation();
  const [rows, setRows] = useState<Talk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showForm, setShowForm] = useState(false);

  // 序号守卫：连续改两行时两次重拉可能乱序返回，旧快照会盖掉刚写成功的值
  const seq = useSeq();
  const reload = () => {
    const n = seq.next();
    api
      .listTalks()
      .then((r) => {
        if (!seq.isCurrent(n)) return;
        setRows(r.rows);
        setLoaded(true);
      })
      .catch((e: Error) => {
        if (seq.isCurrent(n)) setError(e.message);
      });
  };

  useEffect(reload, []);

  // 行内改「是否参加」：改完即存（与面试列表的行内结果下拉同款）
  const setAttend = (id: string, v: string) => {
    api
      .updateTalk(id, { 是否参加: v })
      .then(() => reload())
      .catch((e: Error) => setError(e.message));
  };

  return (
    <div className="flex flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-xs text-muted-foreground">
          {t("talk.summary", { count: rows.length })}
        </p>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <a href={api.talksIcsUrl()} title={t("talk.icsTitle")}>
              <Download size={14} /> {t("talk.exportIcs")}
            </a>
          </Button>
          <Button onClick={() => setShowForm(true)}>
            <Plus size={14} /> {t("talk.add")}
          </Button>
        </div>
      </div>

      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      {/* 三态齐全：骨架 / 空态 / 列表（错误条显示时不与骨架同屏） */}
      {!loaded && !error
        ? [0, 1, 2].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)
        : null}
      {loaded && !error && rows.length === 0 ? (
        <Card className="flex flex-1 flex-col justify-center rounded-lg border-dashed">
          <EmptyState
            icon={<Megaphone size={20} />}
            title={t("talk.emptyTitle")}
            description={t("talk.emptyHint", { action: t("talk.add") })}
          />
        </Card>
      ) : null}

      {rows.map((r) => (
        <Card key={r.宣讲会id} className="rounded-lg p-3.5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {r.公司 || "—"}
              </h3>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {r.时间 || t("talk.whenTbd")}
                {r.形式 && ` · ${domainLabel("talkForm", r.形式, t)}`}
                {r.关联记录 && ` · ${t("interview.related", { value: r.关联记录 })}`}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Select value={r.是否参加} onValueChange={(v) => setAttend(r.宣讲会id, v)}>
                <SelectTrigger
                  className="h-7 w-24 shrink-0 text-xs"
                  aria-label={t("talk.attendAria", { company: r.公司 })}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TALK_ATTEND.map((o) => (
                    <SelectItem key={o} value={o} className="text-xs">
                      {domainLabel("talkAttend", o, t)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {/* 删除（批 D）：预览 → 确认弹窗 → 落盘 */}
              <DeleteRecordButton
                preview={() => previewDeleteRecord("talks", r.宣讲会id)}
                onDeleted={reload}
              />
            </div>
          </div>

          {/* 地点或链接：URL 渲染成可点链接，纯地点按文本显示 */}
          {r.地点或链接 &&
            (/^https?:/i.test(r.地点或链接) ? (
              <a
                href={r.地点或链接}
                target="_blank"
                rel="noreferrer"
                title={t("talk.placeLinkOpen")}
                className="mt-1.5 inline-block text-xs text-primary hover:underline"
              >
                {t("talk.placeLinkOpen")}
              </a>
            ) : (
              <p className="mt-1.5 text-xs text-muted-foreground">{r.地点或链接}</p>
            ))}

          {r.收获 && (
            <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed text-muted-foreground">
              {r.收获}
            </p>
          )}
        </Card>
      ))}

      {showForm && (
        <TalkForm
          onClose={() => setShowForm(false)}
          onSaved={() => {
            setShowForm(false);
            reload();
          }}
        />
      )}
    </div>
  );
}
