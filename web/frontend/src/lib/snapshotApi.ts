// 快照还原与演练的三个端点：**刻意不进 src/api.ts** —— 那个文件登记过水位（460 行，
// 只许变小），窄需求走窄模块（与 lib/bank.ts、hooks/useWorkspaceSync.ts 同一条理由）。
//
// HTTP 封装用 lib/http.ts 的单一实现（自动附 ?ws= 并自检工作区回显，见其注释）。
import type {
  SnapshotInfo,
  SnapshotList,
  SnapshotPreview,
  SnapshotRestoreResult,
} from "./domainTypes";
import { requestJson } from "./http";
import { toMillis } from "./snapshotMeta";

/** 后端时间戳是秒，界面一律用毫秒——换算只在这一处做（见 lib/snapshotMeta.ts）。 */
function normalizeSnapshot(item: SnapshotInfo): SnapshotInfo {
  return { ...item, mtime: toMillis(item.mtime) };
}

/** 可还原的快照清单（新的在前）。 */
export async function listSnapshots(): Promise<SnapshotList> {
  const raw = await requestJson<SnapshotList>("/system/snapshots");
  return { ...raw, snapshots: raw.snapshots.map(normalizeSnapshot) };
}

/** 还原演练：只读，后端保证零写入。 */
export async function previewSnapshot(name: string): Promise<SnapshotPreview> {
  const raw = await requestJson<SnapshotPreview>("/system/snapshots/preview", {
    method: "POST",
    body: { name },
  });
  return { ...raw, mtime: toMillis(raw.mtime) };
}

/** 还原（后端会在锁内先落一份回滚快照，再覆盖同名 + 补齐缺失，从不删除）。 */
export function restoreSnapshot(name: string): Promise<SnapshotRestoreResult> {
  return requestJson<SnapshotRestoreResult>("/system/snapshots/restore", {
    method: "POST",
    body: { name },
  });
}
