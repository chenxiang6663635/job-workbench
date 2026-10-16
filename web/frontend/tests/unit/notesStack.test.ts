// 笔记返回栈（issue #274 三期）的纯逻辑与存储契约。
//
// vitest 跑在 node 环境（没有 sessionStorage）——这里塞一个最小实现，只测
// **纯逻辑与读写口径**：入栈 / 出栈 / 上限、脏值解析、工作区隔离。真正在意的
// 不是存储本身，而是「三条进入路径压同一摞栈」时顺序不乱、以及换工作区不会
// 把别处的路径搬过来（与 notesView.test.ts 同款姿势）。

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { NotesActive } from "../../src/lib/notes";
import {
  NOTES_STACK_LIMIT,
  parseNotesStack,
  popStack,
  pushStack,
  readNotesStack,
  rememberFrom,
  writeNotesStack,
} from "../../src/lib/notesStack";

class MemoryStorage {
  private map = new Map<string, string>();
  get length() {
    return this.map.size;
  }
  key(index: number): string | null {
    return Array.from(this.map.keys())[index] ?? null;
  }
  getItem(name: string): string | null {
    return this.map.get(name) ?? null;
  }
  setItem(name: string, value: string): void {
    this.map.set(name, String(value));
  }
  removeItem(name: string): void {
    this.map.delete(name);
  }
  clear(): void {
    this.map.clear();
  }
}

const storage = new MemoryStorage();

function useStorage(): void {
  (globalThis as { sessionStorage?: Storage }).sessionStorage = storage as unknown as Storage;
  storage.clear();
}

const note = (rel: string, section: NotesActive["section"] = "interview"): NotesActive => ({
  section,
  rel,
});

describe("pushStack / popStack（纯逻辑）", () => {
  it("入栈追加；出栈返回栈顶与剩余", () => {
    const one = pushStack([], note("a.md"));
    const two = pushStack(one, note("b.md"));
    expect(two).toEqual([note("a.md"), note("b.md")]);

    const { previous, rest } = popStack(two);
    expect(previous).toEqual(note("b.md"));
    expect(rest).toEqual([note("a.md")]);
  });

  it("空栈出栈是 null + 空数组——调用方据此不渲染入口", () => {
    expect(popStack([])).toEqual({ previous: null, rest: [] });
  });

  it("与栈顶同一篇不再压：点同一条互链两次只多一步，返回不该原地踏步", () => {
    const stack = pushStack([note("a.md")], note("a.md"));
    expect(stack).toEqual([note("a.md")]);
  });

  it("超上限丢最旧的（会话内栈，退回第 50 步已无意义，但要挡住无限增长）", () => {
    let stack: NotesActive[] = [];
    for (let i = 0; i <= NOTES_STACK_LIMIT; i += 1) stack = pushStack(stack, note(`f${i}.md`));
    expect(stack).toHaveLength(NOTES_STACK_LIMIT);
    expect(stack[0]).toEqual(note("f1.md"));
    expect(stack[stack.length - 1]).toEqual(note(`f${NOTES_STACK_LIMIT}.md`));
  });

  it("不改动入参（纯函数：setState 的 updater 里拿到的旧值必须原样）", () => {
    const before = [note("a.md")];
    pushStack(before, note("b.md"));
    popStack(before);
    expect(before).toEqual([note("a.md")]);
  });
});

describe("rememberFrom（该记的来处是哪一篇）", () => {
  it("落点与当前不同 → 记的是当前这一篇", () => {
    expect(rememberFrom(note("a.md"), note("b.md"))).toEqual(note("a.md"));
  });

  it("点的是当前这一篇 → null（没有上一篇可退，不该凭空多出一步）", () => {
    expect(rememberFrom(note("a.md"), note("a.md"))).toBeNull();
  });

  it("跨 section 的同名文件是两篇（section 参与同一篇判定）", () => {
    expect(rememberFrom(note("a.md", "knowledge"), note("a.md"))).toEqual(
      note("a.md", "knowledge")
    );
  });

  it("还没有当前篇（首次挂载 / 默认选中未落定）→ null", () => {
    expect(rememberFrom(null, note("a.md"))).toBeNull();
  });
});

describe("parseNotesStack（脏值一律当没存过）", () => {
  it("合法项保留，含跨 section", () => {
    const raw = JSON.stringify({
      ws: "ws",
      entries: [note("a.md"), note("图/速查卡.md", "knowledge")],
    });
    expect(parseNotesStack(raw, "ws")).toEqual([note("a.md"), note("图/速查卡.md", "knowledge")]);
  });

  it("非 JSON / 非对象 / 缺 entries / 换工作区 → 空栈", () => {
    expect(parseNotesStack(null, "ws")).toEqual([]);
    expect(parseNotesStack("{不是 json", "ws")).toEqual([]);
    expect(parseNotesStack(JSON.stringify({ ws: "ws" }), "ws")).toEqual([]);
    expect(parseNotesStack(JSON.stringify({ ws: "other", entries: [note("a.md")] }), "ws")).toEqual(
      []
    );
  });

  it("逐项校验：缺字段 / 未知 section / 越界 rel 的项被丢掉，好项留着", () => {
    const raw = JSON.stringify({
      ws: "ws",
      entries: [
        { rel: "a.md" },
        { section: "interview" },
        { section: "01_岗位池", rel: "x.md" },
        { section: "interview", rel: "../../etc/passwd" },
        { section: "interview", rel: "/绝对.md" },
        { section: "interview", rel: "" },
        note("b.md"),
      ],
    });
    expect(parseNotesStack(raw, "ws")).toEqual([note("b.md")]);
  });
});

describe("返回栈的会话内存储", () => {
  beforeEach(useStorage);
  afterEach(() => storage.clear());

  it("写后读回一致", () => {
    writeNotesStack("ws", [note("a.md"), note("b.md", "knowledge")]);
    expect(readNotesStack("ws")).toEqual([note("a.md"), note("b.md", "knowledge")]);
  });

  it("按工作区隔离：换工作区读到空栈（一个键存一个工作区，不串）", () => {
    writeNotesStack("ws", [note("a.md")]);
    expect(readNotesStack("ws")).toEqual([note("a.md")]);
    expect(readNotesStack("other")).toEqual([]);
    expect(storage.length).toBe(1);
  });

  it("没存过 / 存储不可用都不抛，返回空栈", () => {
    expect(readNotesStack("ws")).toEqual([]);
    (globalThis as { sessionStorage?: Storage }).sessionStorage = undefined;
    expect(readNotesStack("ws")).toEqual([]);
    expect(() => writeNotesStack("ws", [note("a.md")])).not.toThrow();
  });
});
