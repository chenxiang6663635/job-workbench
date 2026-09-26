import { describe, expect, it } from "vitest";
import { reminderLines } from "../../src/lib/reminderMeta";
import type { RemindersDue } from "../../src/lib/domainTypes";

/** 造一份最小可用的端点答复（列表内容与判定无关：判定只看 counts）。 */
function due(counts: Partial<RemindersDue["counts"]> = {}): RemindersDue {
  return {
    date: "2026-09-26",
    workspace: "demo",
    window: 3,
    counts: { todos: 0, talks: 0, overdue: 0, ...counts },
    todos: [],
    talks: [],
    overdue: [],
  };
}

describe("reminderLines（提醒条的显示判定）", () => {
  it("没有任何到点事项 → 空数组（整条不渲染，不留空壳）", () => {
    expect(reminderLines(due())).toEqual([]);
  });

  it("null（后端未答 / 拉取失败）→ 空数组，不抛错", () => {
    expect(reminderLines(null)).toEqual([]);
  });

  it("缺 counts 的畸形答复 → 空数组且不抛错（否则会被 ErrorBoundary 升级为整站报错）", () => {
    const broken = { date: "2026-09-26", workspace: "demo", window: 3 } as RemindersDue;
    expect(reminderLines(broken)).toEqual([]);
  });

  it("只有已过期 → 一条 alert，跳追踪表", () => {
    expect(reminderLines(due({ overdue: 2 }))).toEqual([
      {
        kind: "overdue",
        count: 2,
        href: "#applications",
        labelKey: "reminder.overdue",
        severity: "alert",
      },
    ]);
  });

  it("三类齐全 → 顺序为 逾期 / 待办 / 宣讲会（最急的在前）", () => {
    const lines = reminderLines(due({ overdue: 1, todos: 2, talks: 3 }));
    expect(lines.map((line) => line.kind)).toEqual(["overdue", "todos", "talks"]);
    expect(lines.map((line) => line.severity)).toEqual(["alert", "warn", "warn"]);
  });

  it("只有待办/宣讲会时没有 alert（整条保持 warning 档）", () => {
    const lines = reminderLines(due({ todos: 1, talks: 1 }));
    expect(lines.some((line) => line.severity === "alert")).toBe(false);
  });

  it("宣讲会跳「准备」页，待办与逾期都跳追踪表", () => {
    const lines = reminderLines(due({ overdue: 1, todos: 1, talks: 1 }));
    const href = (kind: string) => lines.find((line) => line.kind === kind)?.href;
    expect(href("talks")).toBe("#prepare");
    expect(href("todos")).toBe("#applications");
    expect(href("overdue")).toBe("#applications");
  });

  it("计数为 0 的来源不出现（不显示「0 条已过期」）", () => {
    const lines = reminderLines(due({ todos: 5 }));
    expect(lines).toHaveLength(1);
    expect(lines[0].kind).toBe("todos");
  });
});
