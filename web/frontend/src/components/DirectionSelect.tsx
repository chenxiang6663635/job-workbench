import { useTranslation } from "react-i18next";

import { useDirectionOptions } from "../hooks/useDirectionOptions";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** 记录里已经用过的值（编辑老记录时，别让它从下拉里消失）。 */
  used?: string[];
  disabled?: boolean;
  /** 对话框里的紧凑触发钮（`h-8 text-xs`）。 */
  triggerClassName?: string;
}

/**
 * 方向下拉：候选来自当前工作区装入的方向 + 后端恒接受值 + 已用值（2026-09-30）。
 *
 * 为什么单独一个组件：同一件事此前在四个地方各写一遍（三处表单 + 过滤器的通用组），
 * 每处都直接 map 写死的枚举——插件装的第三个方向永远冒不出来。这里收一处，
 * 表单三处直接用它；过滤器那处因为有「全部」哨兵值，走自己的一行选项合成。
 */
export default function DirectionSelect({
  value,
  onChange,
  used = [],
  disabled = false,
  triggerClassName = "",
}: Props) {
  const { t } = useTranslation();
  const options = useDirectionOptions(used);
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger className={triggerClassName}>
        <SelectValue placeholder={t("form.phDirection")} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
