import { describe, expect, it } from "vitest";

import { buildDirectionOptions } from "../../src/lib/directionOptions";

// 方向候选的合成规则（2026-09-30）：工作区装入的方向 ∪ 后端恒接受值 ∪ 记录已用值。
// 三条都钉住——少任何一条都会在界面上表现为「选不到」或「选了被拒 / 被静默改值」。
describe("buildDirectionOptions", () => {
  const items = [
    { id: "backend", title: "后端 / 服务端" },
    { id: "data", title: "数据 / 算法" },
  ];

  it("空工作区：只剩恒接受值与已用值", () => {
    const options = buildDirectionOptions({
      items: [],
      alwaysAccepted: ["other"],
      used: [],
    });
    expect(options.map((o) => o.value)).toEqual(["other"]);
  });

  it("有标题的方向显示成 `标题（原始值）`", () => {
    const options = buildDirectionOptions({
      items,
      alwaysAccepted: [],
      used: [],
    });
    expect(options[0]).toEqual({ value: "backend", label: "后端 / 服务端（backend）" });
  });

  it("无标题回退到调用方给的文案；再没有就原样显示原始值", () => {
    const options = buildDirectionOptions({
      items: [{ id: "thermal-fluid-cfd", title: "" }],
      alwaysAccepted: ["other"],
      used: ["legacy-dir"],
      fallbackLabel: (value) => (value === "other" ? "其他方向" : value),
    });
    expect(options.map((o) => o.label)).toEqual([
      "thermal-fluid-cfd",
      "其他方向",
      "legacy-dir",
    ]);
  });

  it("已用过的值补在后面，且去重（老记录换了插件也选得到自己的值）", () => {
    const options = buildDirectionOptions({
      items,
      alwaysAccepted: ["other"],
      used: ["hvac", "backend", "other", ""],
    });
    expect(options.map((o) => o.value)).toEqual(["backend", "data", "other", "hvac"]);
  });

  it("顺序稳定：装入的 → 恒接受 → 已用（同一次入参给两次结果一样）", () => {
    const input = { items, alwaysAccepted: ["other"], used: ["hvac"] };
    expect(buildDirectionOptions(input)).toEqual(buildDirectionOptions(input));
  });
});
