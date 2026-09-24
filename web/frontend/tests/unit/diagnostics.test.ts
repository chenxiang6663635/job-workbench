import { describe, expect, it } from "vitest";

import { diagnosticsUrl } from "../../src/lib/diagnostics";

// 下载链接不带 ws 时后端会用**默认工作区**（personal）出包——那正是 issue #22 的形态：
// 界面显示 A、导出的却是 B 的内容。所以这两条断言是真实回归网，不是形式主义。
describe("diagnosticsUrl", () => {
  it("未选工作区时不带 ws（后端回退默认工作区）", () => {
    expect(diagnosticsUrl("")).toBe("/api/system/diagnostics");
  });

  it("选中工作区时带上 ws，并做 URL 编码", () => {
    expect(diagnosticsUrl("我的 工作区")).toBe(
      "/api/system/diagnostics?ws=%E6%88%91%E7%9A%84%20%E5%B7%A5%E4%BD%9C%E5%8C%BA"
    );
  });
});
