import { describe, expect, it } from "vitest";

import { parseImportDiff } from "../../src/lib/bankDiff";

// 导入预览差异表（C-3）：判定是"能不能确定性解析"——解析成功才分色渲染，
// 任何一处对不上就回落 <pre>（用户照着这张表决定要不要落盘，宁可丑不可错）。
const HEADER = "| 题目 | 领域 | 科目 | 来源 |";
const SEP = "|---|---|---|---|";

describe("parseImportDiff（导入预览差异表）", () => {
  it("四列齐全时按末列分类", () => {
    const table = parseImportDiff([
      HEADER,
      SEP,
      "| 缓存穿透 | 技术面 | 缓存 | 导入 |",
      "| MySQL 索引 | 技术面 | 数据库 | 已存在，跳过（03/a.md） |",
      "| 半截题 | — | — | 跳过：正文为空 |",
      "| — | — | — | 提示：忽略了未知列 X |",
    ]);
    expect(table?.rows.map((row) => row.kind)).toEqual(["add", "dup", "skip", "hint"]);
    // 原文完整保留（渲染时截断显示 + title 悬停看全）
    expect(table?.rows[1].cells[3]).toBe("已存在，跳过（03/a.md）");
    expect(table?.header).toEqual(["题目", "领域", "科目", "来源"]);
  });

  it("CSV 导入的来源值同样算新增", () => {
    const table = parseImportDiff([HEADER, SEP, "| 题 | — | — | CSV 导入 |"]);
    expect(table?.rows[0].kind).toBe("add");
  });

  it("表头不对 / 列数不符 / 末列认不出 → null（回落 pre）", () => {
    // 更新预览的字段表：表头不同，走不到分色
    expect(parseImportDiff(["| 字段 | 值 |", "|---|---|", "| 题目 | x |"])).toBeNull();
    // 数据行列数不符
    expect(parseImportDiff([HEADER, SEP, "| 三列 | 而已 | x |"])).toBeNull();
    // 末列无法归类
    expect(parseImportDiff([HEADER, SEP, "| 题 | 领域 | 科目 | 无法归类 |"])).toBeNull();
    // 没有数据行
    expect(parseImportDiff([HEADER, SEP])).toBeNull();
  });

  it("一行坏掉 = 整表回落（全有全无语义）", () => {
    expect(
      parseImportDiff([HEADER, SEP, "| 好 | — | — | 导入 |", "| 坏 | 只两列 |"])
    ).toBeNull();
  });

  it("「提示」优先于「跳过」：正文带『跳过』字样的提示行仍归提示", () => {
    const table = parseImportDiff([
      HEADER,
      SEP,
      "| — | — | — | 提示：忽略了未知列 跳过原因 |",
    ]);
    expect(table?.rows[0].kind).toBe("hint");
  });

  it("真实形态：第 N 行跳过 / 第 N 行没有题目", () => {
    const table = parseImportDiff([
      HEADER,
      SEP,
      "| — | — | — | 第 2 行跳过：字段不合法 |",
      "| — | — | — | 第 5 行没有题目，跳过 |",
    ]);
    expect(table?.rows.map((row) => row.kind)).toEqual(["skip", "skip"]);
  });
});
