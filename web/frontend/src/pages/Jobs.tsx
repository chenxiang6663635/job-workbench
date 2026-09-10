import { useEffect, useState } from "react";
import { Inbox, Link2, Loader2, Plus } from "lucide-react";
import { api } from "../api";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input, Textarea } from "../components/ui/input";
import { Skeleton } from "../components/ui/skeleton";
import { ErrorBanner } from "../components/ErrorBanner";
import JobCard from "../components/JobCard";
import JobDetailView from "../components/JobDetailView";

export default function Jobs() {
  const [items, setItems] = useState<Awaited<ReturnType<typeof api.listJobs>>["items"]>([]);
  const [detail, setDetail] = useState<Awaited<ReturnType<typeof api.jobDetail>> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [draft, setDraft] = useState({ 公司: "", 岗位: "", JD文本: "" });
  // JD 链接抓取（第三批）：尽力而为，失败即明确降级提示手动粘贴
  const [jdUrl, setJdUrl] = useState("");
  const [fetching, setFetching] = useState(false);

  const load = () => {
    setLoading(true);
    api
      .listJobs()
      .then(
        (r) => setItems(r.items),
        (e: Error) => setError(e.message)
      )
      .then(() => setLoading(false));
  };

  useEffect(load, []);

  // 详情拉取期间补 loading 态：此前点击到返回前无任何骨架，像卡住
  const open = (dir: string) => {
    setDetailLoading(true);
    api
      .jobDetail(dir)
      .then((d) => setDetail(d))
      .catch((e: Error) => setError(e.message))
      .then(() => setDetailLoading(false));
  };

  const closeDetail = () => {
    setDetail(null);
    setExpanded(null);
  };

  // 抓取成功后后端已写入 JD原文.md，直接打开详情让用户核对原文——
  // 抓取只是省掉复制粘贴，内容仍必须由用户过目（不做任何改写或摘要）
  const fetchJd = () => {
    if (!draft.公司.trim() || !draft.岗位.trim()) {
      setError("抓取前先填公司与岗位（决定 JD 存在哪个岗位目录）");
      return;
    }
    setFetching(true);
    setError(null);
    api
      .fetchJd({ url: jdUrl.trim(), 公司: draft.公司.trim(), 岗位: draft.岗位.trim() })
      .then((r) => {
        setFetching(false);
        setCreating(false);
        setJdUrl("");
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
        open(r.dir);
      })
      .catch((e: Error) => {
        setError(e.message);
        setFetching(false);
      });
  };

  const submit = () => {
    api
      .createJob(draft)
      .then(() => {
        setCreating(false);
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
        load();
      })
      .catch((e: Error) => setError(e.message));
  };

  if (detail) {
    return (
      <JobDetailView
        detail={detail}
        expanded={expanded}
        onToggleDimension={(name) => setExpanded(expanded === name ? null : name)}
        onBack={closeDetail}
      />
    );
  }

  if (detailLoading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} onClose={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          共 {items.length} 个岗位，评分由 AI 完成写入解析卡后展示
        </p>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} /> 新建岗位
        </Button>
      </div>

      {creating && (
        <Card className="space-y-3 border-primary/30 p-5">
          <div className="grid gap-3 sm:grid-cols-2">
            <Input
              placeholder="公司名称"
              value={draft.公司}
              onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
            />
            <Input
              placeholder="岗位名称"
              value={draft.岗位}
              onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
            />
          </div>
          {/* JD 链接抓取：省掉复制粘贴，但抓不到会直说，不假装成功 */}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              className="flex-1"
              placeholder="JD 网页链接（选填）：https://… 抓取成功后自动存为 JD原文.md"
              value={jdUrl}
              onChange={(e) => setJdUrl(e.target.value)}
            />
            <Button
              variant="outline"
              onClick={fetchJd}
              disabled={
                fetching || !jdUrl.trim() || !draft.公司.trim() || !draft.岗位.trim()
              }
              title={!draft.公司.trim() || !draft.岗位.trim() ? "先填公司与岗位" : "抓取网页正文"}
            >
              {fetching ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
              {fetching ? "抓取中…" : "从链接抓取"}
            </Button>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground/70">
            只取网页正文，不做改写或摘要。需登录、有反爬或纯 JS 渲染的页面抓不到，
            会明确提示你手动粘贴——不会把半截内容当成抓取成功。
          </p>
          <Textarea
            className="min-h-[12rem] resize-y font-mono text-xs leading-relaxed"
            placeholder="粘贴完整的 JD 原文（含岗位职责与任职要求）。原文会被完整保存，不做改写或摘要。"
            value={draft.JD文本}
            onChange={(e) => setDraft({ ...draft, JD文本: e.target.value })}
          />
          <div className="flex gap-2">
            <Button
              onClick={submit}
              disabled={
                !draft.公司.trim() || !draft.岗位.trim() || !draft.JD文本.trim()
              }
            >
              保存岗位
            </Button>
            <Button variant="ghost" onClick={() => setCreating(false)}>
              取消
            </Button>
          </div>
        </Card>
      )}

      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card className="flex flex-col items-center gap-2 p-10 text-center">
          <Inbox size={28} className="text-muted-foreground" />
          <p className="text-base font-medium text-foreground">岗位池还是空的</p>
          <p className="mt-2 text-sm text-muted-foreground">
            点击「新建岗位」粘贴一份 JD，随后让 AI 生成解析卡，即可看到匹配度评分。
          </p>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((job) => (
            <JobCard key={job.dir} job={job} onOpen={() => open(job.dir)} />
          ))}
        </div>
      )}
    </div>
  );
}
