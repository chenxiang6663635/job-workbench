import { describe, expect, it } from "vitest";

import { parseNotesPos } from "../../src/lib/notesView";

// 阅读位置的**解析**是纯函数（读写本身要 sessionStorage，留给真浏览器）。
// 存储里的东西可能是旧版、被手改过、或者被换过的账户写进去的——一律按"没存过"
// 处理，宁可不恢复，也不要滚到一个错的地方。

describe("parseNotesPos（存储里的阅读位置）", () => {
  it("空值与坏 JSON 都当没存过", () => {
    expect(parseNotesPos(null)).toBeNull();
    expect(parseNotesPos("")).toBeNull();
    expect(parseNotesPos("{不是 JSON")).toBeNull();
  });

  it("没有 section / rel 的位置不可用——没有坐标就等于没记", () => {
    expect(parseNotesPos(JSON.stringify({ ws: "w", line: 12, offset: -40 }))).toBeNull();
    expect(parseNotesPos(JSON.stringify({ ws: "w", section: "interview" }))).toBeNull();
  });

  it("完整位置按原样解析", () => {
    expect(
      parseNotesPos(
        JSON.stringify({ ws: "w", section: "interview", rel: "a/b.md", line: 12, offset: -40 })
      )
    ).toEqual({ ws: "w", section: "interview", rel: "a/b.md", line: 12, offset: -40 });
  });

  it("缺 line / offset 时回落到默认值——仍知道在哪一篇，只是不动滚动条", () => {
    expect(parseNotesPos(JSON.stringify({ section: "interview", rel: "a/b.md" }))).toEqual({
      ws: "",
      section: "interview",
      rel: "a/b.md",
      line: null,
      offset: 0,
    });
  });
});
