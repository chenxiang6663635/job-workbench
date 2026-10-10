// 数据根三态（读回 / 记住 / 清除）：`GET|POST|DELETE /api/system/data-root`。
//
// 为什么单独成文件：`api.ts` 是登记过水位的存量文件（只许变小）；而这三个动作与
// 卡上的「迁移事务」是同一件事的两个面——响应都是 `dataroot.describe()` 的同一份
// 诊断对象。与 credentialApi / snapshotApi / providerApi 同款的小模块先例。
//
// 失效态（unavailable）下这三条是**唯一**的明路：迁移走不了（源根不可用），
// 用户要么把路径改回可写、要么重选一个、要么清除已保存的选择。
import { requestJson } from "./http";
import type { DataRootDiagnostic } from "./domainTypes";

/** 读回诊断（失效态照常可用——要找失败原因的是人）。 */
export function getDataRoot(): Promise<DataRootDiagnostic> {
  return requestJson<DataRootDiagnostic>("/system/data-root");
}

/** 记住数据根（只接受绝对路径；校验在服务端 `dataroot.write_persisted_selection`）。 */
export function setDataRoot(path: string): Promise<DataRootDiagnostic> {
  return requestJson<DataRootDiagnostic>("/system/data-root", {
    method: "POST",
    body: { path },
  });
}

/** 清除持久化选择（幂等）——回到默认数据根。 */
export function clearDataRoot(): Promise<DataRootDiagnostic> {
  return requestJson<DataRootDiagnostic>("/system/data-root", { method: "DELETE" });
}
