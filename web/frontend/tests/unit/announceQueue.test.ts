import { describe, expect, it } from "vitest";
import { ANNOUNCE_GAP_MS, createAnnounceQueue } from "../../src/lib/announceQueue";

/**
 * 队列是「读屏能不能听到每一句」的最后一环（2026-09-22 审查 MINOR 笔 2）。
 * 单测直接驱动 scheduler：同帧连发不吞句、空串不进队、相邻两条留间隔、dispose 静默。
 */
function fakeScheduler() {
  const tasks: { fn: () => void; ms: number }[] = [];
  return {
    tasks,
    setTimeout: (fn: () => void, ms: number) => {
      tasks.push({ fn, ms });
      return tasks.length;
    },
    clearTimeout: () => {},
    runNext() {
      const task = tasks.shift();
      if (task) task.fn();
    },
    runAll() {
      while (tasks.length) this.runNext();
    },
  };
}

describe("announceQueue", () => {
  it("同帧连发两条：先清零再逐条落文本，谁都不被吞", () => {
    const seen: string[] = [];
    const sched = fakeScheduler();
    const queue = createAnnounceQueue((text) => seen.push(text), sched);

    queue.push("A");
    queue.push("B");
    sched.runAll();

    expect(seen).toEqual(["", "A", "", "B"]);
  });

  it("空串与纯空白不进队、不安排计时器", () => {
    const seen: string[] = [];
    const sched = fakeScheduler();
    const queue = createAnnounceQueue((text) => seen.push(text), sched);

    queue.push("");
    queue.push("   ");

    expect(sched.tasks).toEqual([]);
    expect(seen).toEqual([]);
  });

  it("相邻两条之间等一个 GAP，避免被读屏合并成一句", () => {
    const sched = fakeScheduler();
    const queue = createAnnounceQueue(() => {}, sched);

    queue.push("A");
    queue.push("B");
    sched.runNext(); // step：清空
    sched.runNext(); // 落文本 A → 队列里还有 B，下一步要等 GAP

    expect(sched.tasks.map((t) => t.ms)).toEqual([ANNOUNCE_GAP_MS]);
  });

  it("dispose 之后待播内容不再落地", () => {
    const seen: string[] = [];
    const sched = fakeScheduler();
    const queue = createAnnounceQueue((text) => seen.push(text), sched);

    queue.push("A");
    queue.dispose();
    sched.runAll();

    expect(seen).toEqual([]);
  });
});
