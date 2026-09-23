import { useTranslation } from "react-i18next";
import { FileCheck, FileDown, Loader2, PenLine, Save } from "lucide-react";

import { api, type ResumeVersion } from "../api";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

interface Props {
  version: string;
  versions: ResumeVersion[];
  onVersionChange: (next: string) => void;
  layout: string;
  accent: string;
  saving: boolean;
  onSave: () => void;
  building: boolean;
  buildBlocked: boolean;
  onBuild: () => void;
  onRewrite: () => void;
}

/**
 * 简历页顶部的操作条：版本选择 + 保存 / 生成 / AI 改写 / 导出 Word。
 *
 * 从 `pages/Resume.tsx` 拆出：那一页在 size_allowlist 的存量豁免线上（水位只许
 * 变小），而版本切换的竞态守卫（旧版本的数据不许存进新版本文件）必须加进去——
 * 不动这些 JSX 就没地方放。
 */
export default function ResumeToolbar({
  version,
  versions,
  onVersionChange,
  layout,
  accent,
  saving,
  onSave,
  building,
  buildBlocked,
  onBuild,
  onRewrite,
}: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Select value={version} onValueChange={onVersionChange}>
        <SelectTrigger className="w-40" aria-label={t("resume.selectVersion")}>
          <SelectValue placeholder={t("resume.selectVersion")} />
        </SelectTrigger>
        <SelectContent>
          {versions.map((v) => (
            <SelectItem key={v.version} value={v.version}>
              {v.version}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button variant="outline" onClick={onSave} disabled={saving}>
        <Save size={15} /> {saving ? t("common.saving") : t("common.save")}
      </Button>

      <Button
        onClick={onBuild}
        disabled={building || buildBlocked}
        title={t(buildBlocked ? "resume.buildBlocked" : "resume.buildTitle")}
      >
        {building ? <Loader2 size={15} className="animate-spin" /> : <FileCheck size={15} />}
        {building ? t("resume.building") : t("resume.buildPdf")}
      </Button>

      <Button variant="outline" onClick={onRewrite} title={t("resume.rewriteTitle")}>
        <PenLine size={15} /> {t("resume.aiRewrite")}
      </Button>

      {/* Word 版定位是「文本搬运」：方便网申系统粘贴。零依赖 .doc，排版还原度
          有限——这一句必须在按钮旁说清，不让用户误当正式交付物 */}
      <Button variant="outline" asChild>
        <a
          href={api.resumeDocUrl(version, { template: layout, accent })}
          download
          title={t("resume.wordTitle")}
        >
          <FileDown size={15} /> {t("resume.exportWord")}
        </a>
      </Button>
      <span className="text-[11px] text-muted-foreground">{t("resume.wordTitle")}</span>
    </div>
  );
}
