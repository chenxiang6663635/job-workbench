import { useEffect, useState } from "react";
import { api } from "../api";

// UX-3：投递 id → 岗位池目录名，供投递行的「查看解析卡」用。
//
// **键必须是后端自己的关联结果**（`JobSummary.applicationId`），不能用前端拼出来的
// (公司, 岗位)：卡片里展示的公司 / 岗位来自解析卡「基本信息」，与追踪表里的写法
// 常常不同（真实数据里就对不上），而后端自己匹配用的是**目录名拆分 + dedup_key
// （trim + 小写）**——拿展示名当键会系统性失配，最值得点进去看的那批岗位
// （已评分、解析卡填了基本信息）反而没有入口（独立审查 MAJOR）。
//
// 单独成 hook：Applications 页已在规模闸门的水位上，这里顺手少占二十行。
// 拉不到（后端没起 / 岗位池为空）就退化成空表：入口不出现，投递表照常可用。
export function useJobDirs(): Record<string, string> {
  const [jobDirs, setJobDirs] = useState<Record<string, string>>({});
  useEffect(() => {
    api.listJobs({}).then(
      (r) => {
        const next: Record<string, string> = {};
        for (const job of r.items) {
          if (job.applicationId) next[job.applicationId] = job.dir;
        }
        setJobDirs(next);
      },
      () => setJobDirs({})
    );
  }, []);
  return jobDirs;
}
