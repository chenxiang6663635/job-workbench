import { describe, expect, it } from "vitest";

import {
  buildNotesTree,
  classifyNotesFile,
  extractOutline,
  filterNotes,
  findAnchorLine,
  stripHtmlComments,
} from "../../src/lib/notes";

describe("findAnchorLine（命中行 → 该滚到哪个块）", () => {
  it("命中落在块中间时取该块的起始行", () => {
    expect(findAnchorLine([1, 10, 20], 15)).toBe(10);
  });
  it("命中正好是块起始行时取它自己", () => {
    expect(findAnchorLine([1, 10, 20], 10)).toBe(10);
  });
  it("命中早于首个块时退回首个块——不原地不动", () => {
    expect(findAnchorLine([5, 10], 1)).toBe(5);
  });
  it("一个块都没有时返回 null", () => {
    expect(findAnchorLine([], 3)).toBeNull();
  });
});

const file = (rel: string, size = 10) => ({
  rel,
  name: rel.split("/").pop() ?? rel,
  size,
  mtime: 0,
});

describe("buildNotesTree（平铺 rel → 树）", () => {
  const tree = buildNotesTree([
    {
      key: "interview",
      items: [
        file("README.md"),
        file("空文件.md", 0),
        file("行为面/_模板_行为故事.md"),
        file("行为面/缓存雪崩.md"),
        file("自我介绍/自我介绍.md"),
      ],
    },
  ]);

  it("README 置顶、目录先于文件、组内按名称确定排序", () => {
    expect(tree.interview.map((n) => n.name)).toEqual([
      "README",
      "自我介绍",
      "行为面",
      "空文件",
    ]);
  });

  it("目录内文件带角色标记（_模板_ 是样板、README 是目录说明）", () => {
    const behavior = tree.interview.find((n) => n.name === "行为面");
    expect(behavior?.children?.map((n) => n.name)).toEqual([
      "_模板_行为故事",
      "缓存雪崩",
    ]);
    expect(behavior?.children?.[0].fileKind).toBe("template");
    expect(behavior?.children?.[1].fileKind).toBe("doc");
    expect(tree.interview[0].fileKind).toBe("readme");
  });

  it("0 字节文件照常保留（大小留给渲染层做「空」标记，文件不能消失）", () => {
    const empty = tree.interview.find((n) => n.name === "空文件");
    expect(empty?.kind).toBe("file");
    expect(empty?.size).toBe(0);
  });

  it("空列表建出空树；另一 section 互不影响", () => {
    const out = buildNotesTree([
      { key: "interview", items: [] },
      { key: "knowledge", items: [file("Redis 速查卡.md")] },
    ]);
    expect(out.interview).toEqual([]);
    expect(out.knowledge.map((n) => n.name)).toEqual(["Redis 速查卡"]);
  });
});

describe("classifyNotesFile（工作区命名约定）", () => {
  it("README / 模板 / 示例 / 正文四类", () => {
    expect(classifyNotesFile("README.md")).toBe("readme");
    expect(classifyNotesFile("readme.md")).toBe("readme");
    expect(classifyNotesFile("_模板_自我介绍.md")).toBe("template");
    expect(classifyNotesFile("_示例_解析卡.md")).toBe("example");
    expect(classifyNotesFile("缓存雪崩的 40 分钟.md")).toBe("doc");
  });
});

describe("filterNotes", () => {
  const tree = buildNotesTree([
    {
      key: "interview",
      items: [file("行为面/缓存雪崩.md"), file("自我介绍/自我介绍.md")],
    },
  ]).interview;

  it("命中文件保留其祖先目录，未命中组消失", () => {
    const hit = filterNotes(tree, "缓存");
    expect(hit.map((n) => n.name)).toEqual(["行为面"]);
    expect(hit[0].children?.map((n) => n.name)).toEqual(["缓存雪崩"]);
  });

  it("命中目录名时整组保留", () => {
    const hit = filterNotes(tree, "行为");
    expect(hit.map((n) => n.name)).toEqual(["行为面"]);
    expect(hit[0].children).toHaveLength(1);
  });

  it("空查询原样返回（引用不变）", () => {
    expect(filterNotes(tree, "   ")).toBe(tree);
  });

  it("无命中返回空数组", () => {
    expect(filterNotes(tree, "不存在的词")).toEqual([]);
  });
});

describe("extractOutline（h2/h3，锚点=源码行号）", () => {
  it("提取层级与文本，跳过围栏代码块内的 #", () => {
    const md = [
      "# 文档标题不进大纲",
      "",
      "```",
      "# 代码里的注释不是标题",
      "echo hi",
      "```",
      "",
      "## 情境",
      "### 细节",
      "## 行动",
    ].join("\n");
    const outline = extractOutline(md);
    expect(outline.map((o) => [o.level, o.text])).toEqual([
      [2, "情境"],
      [3, "细节"],
      [2, "行动"],
    ]);
    // id 用 1-based 源码行号：`## 情境` 在第 8 行（与渲染侧的 position.start.line 同源）
    expect(outline[0].id).toBe("h-8");
  });

  it("波浪号围栏同样跳过；围栏外恢复提取", () => {
    const md = "~~~\n## 假的\n~~~\n## 真的\n";
    expect(extractOutline(md).map((o) => o.text)).toEqual(["真的"]);
  });

  it("CRLF 与尾部闭合井号", () => {
    const outline = extractOutline("## 标题 ##\r\n### 次节\r\n");
    expect(outline.map((o) => o.text)).toEqual(["标题", "次节"]);
    expect(outline.map((o) => o.id)).toEqual(["h-1", "h-2"]);
  });

  it("行号 1 起（空行也占一行）", () => {
    const md = "# 一\n\n## 二\n";
    expect(extractOutline(md)[0].id).toBe("h-3");
  });

  it("容忍 ≤3 空格缩进的标题（与渲染侧 remark 口径一致）", () => {
    expect(extractOutline("   ## 缩进标题\n").map((o) => o.text)).toEqual(["缩进标题"]);
  });
});

describe("stripHtmlComments（渲染前剥注释，保行数）", () => {
  it("删掉整行与行内注释，行数不变（锚点行号不漂移）", () => {
    const md = "第一行\n<!-- 注释一 -->\n第三行 <!-- 内联 --> 尾\n";
    const out = stripHtmlComments(md);
    expect(out.split("\n")).toHaveLength(4);
    expect(out).not.toContain("注释");
    expect(out).toContain("第三行  尾");
  });

  it("跨行注释整体删除；围栏代码块内不动", () => {
    const md = "```\n<!-- 代码里的示例 -->\n```\n<!--\n跨行\n-->\n之后";
    const out = stripHtmlComments(md);
    expect(out).toContain("<!-- 代码里的示例 -->");
    expect(out).not.toContain("跨行");
    expect(out).toContain("之后");
  });

  it("注释体内出现围栏标记不破坏剥离（围栏判定不对注释态生效）", () => {
    const md = "前\n<!--\n```\n-->\n后\n```\n代码\n```\n";
    const out = stripHtmlComments(md);
    expect(out).not.toContain("<!--");
    // 8 个内容行 + 末尾 \n 切出的空元素 = 9（保行数：输入输出同为 9）
    expect(out.split("\n")).toHaveLength(9);
  });
});
