import { useTranslation } from "react-i18next";

import { BATCHES, DIRECTIONS, STAGES } from "../api";
import { ALL } from "../lib/applicationMeta";
import { domainLabel } from "../lib/domainLabels";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

export interface ApplicationFilterValue {
  stage: string;
  direction: string;
  batch: string;
}

interface Props {
  value: ApplicationFilterValue;
  onChange: (next: ApplicationFilterValue) => void;
}

/**
 * 阶段 / 方向 / 批次三个下拉（Radix Select 不接受空字符串作为 value，「全部」
 * 用哨兵值表达）。从 Applications 页拆出：那一页已在 size_allowlist 的存量豁免
 * 线上，加东西必须先从别处腾出空间。
 */
export default function ApplicationFilters({ value, onChange }: Props) {
  const { t } = useTranslation();

  const groups = [
    {
      field: "stage" as const,
      width: "w-36",
      ariaKey: "app.filterStage",
      allKey: "app.allStages",
      kind: "stage" as const,
      options: STAGES,
    },
    {
      field: "direction" as const,
      width: "w-32",
      ariaKey: "app.filterDirection",
      allKey: "app.allDirections",
      kind: "direction" as const,
      options: DIRECTIONS,
    },
    {
      field: "batch" as const,
      width: "w-32",
      ariaKey: "app.filterBatch",
      allKey: "app.allBatches",
      kind: "batch" as const,
      options: BATCHES,
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
              <SelectItem key={option} value={option}>
                {domainLabel(group.kind, option, t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ))}
    </>
  );
}
