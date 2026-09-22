import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link2, Loader2 } from "lucide-react";
import { api } from "../api";
import { Button } from "./ui/button";
import { Card } from "./ui/card";
import { Input, Textarea } from "./ui/input";

// 新建岗位表单（2026-09-22 自 pages/Jobs.tsx 拆出：岗位页已踩在规模闸门的水位上，
// 这块是整页里最独立的一整块——状态自持、只往外吐结果与失败）。
//
// 两条写入路径共用同一张卡片：
// - 粘贴 JD **直接保存**；
// - 给链接**抓取**——后端抓到就写好 JD原文.md 并返回目录名，父级据此打开详情。
// 抓取只是省掉复制粘贴：内容仍必须由用户过目（不做改写 / 摘要）。
interface JobCreateFormProps {
  /** 保存成功：父级重拉列表（公司 / 岗位回传，用于播报） */
  onCreated: (company: string, role: string) => void;
  /** 抓取成功：父级重拉列表并直接打开该岗位详情 */
  onFetched: (dir: string, company: string, role: string) => void;
  /** 失败统一交给父级的 ErrorBanner（弹窗内另起一套错误条会两处报警） */
  onError: (message: string) => void;
  onClose: () => void;
}

export default function JobCreateForm({
  onCreated,
  onFetched,
  onError,
  onClose,
}: JobCreateFormProps) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState({ 公司: "", 岗位: "", JD文本: "" });
  const [jdUrl, setJdUrl] = useState("");
  const [fetching, setFetching] = useState(false);

  const fetchJd = () => {
    const company = draft.公司.trim();
    const role = draft.岗位.trim();
    if (!company || !role) {
      onError(t("job.fetchNeedCompanyRole"));
      return;
    }
    setFetching(true);
    api
      .fetchJd({ url: jdUrl.trim(), 公司: company, 岗位: role })
      .then((r) => {
        setFetching(false);
        onFetched(r.dir, company, role);
      })
      .catch((e: Error) => {
        onError(e.message);
        setFetching(false);
      });
  };

  const submit = () => {
    const company = draft.公司.trim();
    const role = draft.岗位.trim();
    api
      .createJob(draft)
      .then(() => {
        onCreated(company, role);
        setDraft({ 公司: "", 岗位: "", JD文本: "" });
      })
      .catch((e: Error) => onError(e.message));
  };

  return (
    <Card className="space-y-3 border-primary/30 p-5">
      <div className="grid gap-3 sm:grid-cols-2">
        <Input
          placeholder={t("form.phCompany")}
          value={draft.公司}
          onChange={(e) => setDraft({ ...draft, 公司: e.target.value })}
        />
        <Input
          placeholder={t("form.phRole")}
          value={draft.岗位}
          onChange={(e) => setDraft({ ...draft, 岗位: e.target.value })}
        />
      </div>
      {/* JD 链接抓取：省掉复制粘贴，但抓不到会直说，不假装成功 */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          className="flex-1"
          placeholder={t("job.phJdUrl")}
          value={jdUrl}
          onChange={(e) => setJdUrl(e.target.value)}
        />
        <Button
          variant="outline"
          onClick={fetchJd}
          disabled={fetching || !jdUrl.trim() || !draft.公司.trim() || !draft.岗位.trim()}
          title={
            !draft.公司.trim() || !draft.岗位.trim()
              ? t("job.fetchNeedFillHint")
              : t("job.fetchTitle")
          }
        >
          {fetching ? <Loader2 size={14} className="animate-spin" /> : <Link2 size={14} />}
          {fetching ? t("job.fetching") : t("job.fetchFromUrl")}
        </Button>
      </div>
      <p className="text-[11px] leading-relaxed text-muted-foreground">
        {t("job.fetchNote")}
      </p>
      <Textarea
        className="min-h-[12rem] resize-y font-mono text-xs leading-relaxed"
        placeholder={t("job.phJdText")}
        value={draft.JD文本}
        onChange={(e) => setDraft({ ...draft, JD文本: e.target.value })}
      />
      <div className="flex gap-2">
        <Button
          onClick={submit}
          disabled={!draft.公司.trim() || !draft.岗位.trim() || !draft.JD文本.trim()}
        >
          {t("job.saveJob")}
        </Button>
        <Button variant="ghost" onClick={onClose}>
          {t("common.cancel")}
        </Button>
      </div>
    </Card>
  );
}
