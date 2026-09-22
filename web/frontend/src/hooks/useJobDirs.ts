import { useEffect, useState } from "react";
import { api } from "../api";
import { jobDirKey } from "../lib/applicationMeta";

// UX-3：岗位池目录名反查表（「公司|岗位」→ 目录名），供投递行的「查看解析卡」用。
//
// 单独成 hook 而不写在页面里：Applications 页已在规模闸门的水位上，这里顺手
// 少占二十行；更重要的是它只做一件事——拉一次岗位列表、按同一把键建表。
// 拉不到（后端没起 / 岗位池为空）就退化成空表：入口不出现，投递表照常可用。
export function useJobDirs(): Record<string, string> {
  const [jobDirs, setJobDirs] = useState<Record<string, string>>({});
  useEffect(() => {
    api.listJobs({}).then(
      (r) => {
        const next: Record<string, string> = {};
        for (const job of r.items) next[jobDirKey(job.company, job.role)] = job.dir;
        setJobDirs(next);
      },
      () => setJobDirs({})
    );
  }, []);
  return jobDirs;
}
