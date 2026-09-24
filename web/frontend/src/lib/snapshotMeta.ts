// 快照清单与演练结果的**纯展示逻辑**（首发前收口批 笔 2）。
//
// 为什么要单独一个文件：这三件小事全是"看起来一眼对、边界一测就错"的类型——
// 体积单位换挡、秒/毫秒、以及"这份快照到底值不值得还原"。放进组件里就只能靠
// Playwright 间接覆盖，而它们恰恰是单测能吃下的形状（与 lib/dangerGate.ts 同款理由）。
import type { SnapshotPreview } from "./domainTypes";

/** 后端时间戳（秒，浮点）→ 界面用的毫秒。 */
export function toMillis(seconds: number): number {
  return Math.round(seconds * 1000);
}

/** 字节数 → 人读得懂的量级（B / KB / MB）。 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${Math.round(bytes)} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * 快照时间 → `YYYY-MM-DD HH:mm`（本地时区）。
 *
 * 刻意不用 `toLocaleString()`：它随系统区域变（中文系统 `2026/9/23 22:07`，英文
 * `9/23/2026, 10:07 PM`），同一份界面在不同机器上长得不一样，也让断言无处落脚。
 */
export function formatSnapshotTime(ms: number): string {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** 演练后会让工作区变化的条目数（覆盖 + 新增）。 */
export function pendingChanges(
  preview: Pick<SnapshotPreview, "overwrite" | "add">
): number {
  return preview.overwrite + preview.add;
}

/**
 * 这份快照值不值得还原。
 *
 * 两种情况都算"不值得"，且都必须让按钮不可点：空快照（total === 0，多半是坏包或
 * 来自一个空工作区）、以及与当前内容完全一致（还原等于什么都没做）。让用户点下去
 * 再得到一句"没有变化"是把判断推给人；这里直接拦住并说明理由。
 */
export function canRestore(
  preview: Pick<SnapshotPreview, "overwrite" | "add" | "total">
): boolean {
  return preview.total > 0 && pendingChanges(preview) > 0;
}

/** 演练结果的徽章（跳过为 0 的项——0 不是信息，是噪音）。 */
export function drillBadges(
  preview: Pick<SnapshotPreview, "overwrite" | "add" | "same">
): { key: "overwrite" | "add" | "same"; count: number }[] {
  const all: { key: "overwrite" | "add" | "same"; count: number }[] = [
    { key: "overwrite", count: preview.overwrite },
    { key: "add", count: preview.add },
    { key: "same", count: preview.same },
  ];
  return all.filter((item) => item.count > 0);
}
