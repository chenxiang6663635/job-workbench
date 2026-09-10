import { useEffect, useRef, useState } from "react";
import { api, type Application } from "../api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

/** Radix Select 不接受空串值，用哨兵表示「不关联」 */
const NONE = "__none__";

/**
 * 「关联投递记录」下拉。面试表单与 Offer 表单此前各写一份原生 select +
 * 懒加载 + 带出公司/岗位的逻辑（rule of three 的第 2、3 次）——收敛为一处：
 * 组件自己管记录列表（首次展开时拉一次），选中后把整条记录回传给调用方。
 */
export function ApplicationSelect({
  value,
  onPick,
  emptyLabel = "不关联",
}: {
  /** 当前关联的投递 id，空串表示不关联 */
  value: string;
  onPick: (app: Application | null) => void;
  emptyLabel?: string;
}) {
  const [apps, setApps] = useState<Application[]>([]);
  const loaded = useRef(false);

  const load = () => {
    if (loaded.current) return;
    loaded.current = true; // 用 ref 而非 apps.length 判断：列表本来就可能是空的
    api
      .listApplications({})
      .then((r) => setApps(r.items))
      .catch((e: Error) => console.error("加载投递记录失败", e));
  };

  // 非空初值（编辑既有记录）时也要能显示「id · 公司 岗位」，而不是裸 id
  useEffect(() => {
    if (value) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Select
      value={value || NONE}
      onValueChange={(v) => onPick(v === NONE ? null : apps.find((a) => a.id === v) ?? null)}
      onOpenChange={(open) => {
        if (open) load();
      }}
    >
      <SelectTrigger>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{emptyLabel}</SelectItem>
        {apps.map((a) => (
          <SelectItem key={a.id} value={a.id}>
            {a.id} · {a.公司} {a.岗位}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
