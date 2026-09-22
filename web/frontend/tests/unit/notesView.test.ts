// 批量勾选的本地记忆（C-1）：待提交集合与确认框快照。
//
// vitest 跑在 node 环境（没有 sessionStorage）——这里塞一个最小实现，只测
// **纯逻辑**：键隔离、点选切换、旧快照兼容。真正在意的不是存储本身，而是
// "切文件不清另一个文件的集合"与"老格式读得回来"这两条。

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  clearPendingLines,
  readPendingLines,
  readToggleSnapshot,
  togglePendingLine,
  writePendingLines,
} from "../../src/lib/notesView";

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
  (globalThis as { sessionStorage?: Storage }).sessionStorage =
    storage as unknown as Storage;
  storage.clear();
}

describe("待提交集合", () => {
  beforeEach(useStorage);
  afterEach(() => storage.clear());

  it("按「工作区 + 文件」各自记忆：换文件不清另一个文件的集合", () => {
    writePendingLines("ws", "interview", "a.md", [2, 5]);
    writePendingLines("ws", "interview", "b.md", [7]);

    expect(readPendingLines("ws", "interview", "a.md")).toEqual([2, 5]);
    expect(readPendingLines("ws", "interview", "b.md")).toEqual([7]);
    // 换工作区互不干扰
    expect(readPendingLines("other", "interview", "a.md")).toEqual([]);
  });

  it("点选是切换：再点一次移出集合，结果始终升序", () => {
    expect(togglePendingLine([], 5)).toEqual([5]);
    expect(togglePendingLine([2, 5], 5)).toEqual([2]);
    expect(togglePendingLine([2], 5)).toEqual([2, 5]);
  });

  it("清空只影响这一个文件", () => {
    writePendingLines("ws", "interview", "a.md", [2, 5]);
    writePendingLines("ws", "interview", "b.md", [7]);

    clearPendingLines("ws", "interview", "a.md");

    expect(readPendingLines("ws", "interview", "a.md")).toEqual([]);
    expect(readPendingLines("ws", "interview", "b.md")).toEqual([7]);
  });
});

describe("确认框快照", () => {
  beforeEach(useStorage);
  afterEach(() => storage.clear());

  it("旧格式（line 单数字段）读成 lines 数组——升级瞬间在途的确认框不炸", () => {
    storage.setItem(
      "jobws_notes_flow",
      JSON.stringify({
        ws: "ws",
        section: "interview",
        rel: "a.md",
        line: 3,
        token: "tok",
        summary: "s",
        diff: ["x"],
      })
    );

    const snap = readToggleSnapshot("ws");

    expect(snap).not.toBeNull();
    expect(snap?.lines).toEqual([3]);
    expect(snap?.token).toBe("tok");
  });
});
