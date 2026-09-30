import { useTranslation } from "react-i18next";

import { BATCHES, STAGES } from "../api";
import { ALL } from "../lib/applicationMeta";
import { domainLabel } from "../lib/domainLabels";
import { useDirectionOptions } from "../hooks/useDirectionOptions";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

export interface ApplicationFilterValue {
  stage: string;
  direction: string;
  batch: string;
}

interface Props {
  value: ApplicationFilterValue;
  onChange: (next: ApplicationFilterValue) => void;
  /** 表里已出现过的方向（含老记录的值）——过滤器的候选也要把它们算上。 */
  used?: string[];
}

/**
 * 阶段 / 方向 / 批次三个下拉（Radix Select 不接受空字符串作为 value，「全部」
 * 用哨兵值表达）。从 Applications 页拆出：那一页已在 size_allowlist 的存量豁免
 * 线上，加东西必须先从别处腾出空间。
 *
 * 方向那一组自 2026-09-30 起**不再写死**：候选来自 `useDirectionOptions`
 * （工作区装入的方向 + 后端恒接受值 + 表里已用过的值），与三处表单同一个来源。
 * 三组统一成 `{value, label}`，渲染只写一次。
 */
export default function ApplicationFilters({ value, onChange, used = [] }: Props) {
  const { t } = useTranslation();
  const directionOptions = useDirectionOptions(used);
  const toOptions = (kind: "stage" | "batch", values: string[]) =>
    values.map((option) => ({ value: option, label: domainLabel(kind, option, t) }));

  const groups = [
    {
      field: "stage" as const,
      width: "w-36",
      ariaKey: "app.filterStage",
      allKey: "app.allStages",
      options: toOptions("stage", STAGES),
    },
    {
      field: "direction" as const,
      width: "w-32",
      ariaKey: "app.filterDirection",
      allKey: "app.allDirections",
      options: directionOptions,
    },
    {
      field: "batch" as const,
      width: "w-32",
      ariaKey: "app.filterBatch",
      allKey: "app.allBatches",
      options: toOptions("batch", BATCHES),
    },
  ];

  return (
    <>
      {groups.map((group) => (
        <Select
          key={group.field}
          value={value[group.field] || ALL}
          onValueChange={(v) => onChange({ ...value, [group.field]: v === ALL ? "" : v })}
        >
          <SelectTrigger className={group.width} aria-label={t(group.ariaKey)}>
            <SelectValue placeholder={t(group.allKey)} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t(group.allKey)}</SelectItem>
            {group.options.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}
    </>
  );
}
