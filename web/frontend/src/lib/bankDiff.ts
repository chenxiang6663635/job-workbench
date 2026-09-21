// 题库预览的差异表解析（2026-09-21 批次 C-3）：把导入预览的 Markdown 表格
// （`| 题目 | 领域 | 科目 | 来源 |`）解析成行数据，让界面按状态分色
// （新增 / 已存在 / 跳过 / 提示）——此前一律当纯文本 <pre>，哪几行会真落盘
// 要逐字读完才知道。
//
// **只在能确定性解析时启用**：表头逐字匹配 + 分隔行 + 每行四列 + 末列能归类，
// 任何一条不满足就返回 null、调用方回落 <pre>。解析错了比显示得丑危险得多——
// 用户是照着这张表决定要不要落盘的。其余预览（新增 / 更新 / 删除）的 diff
// 形态不同（字段表），够不到这个表头，自然走不到分色路径。
//
// 末列的分类值（导入 / CSV 导入 / 已存在，跳过… / 跳过：… / 提示：…）由领域层
// 生成（question_bank.preview_import），是**数据**不是界面文案——这里只做归类，
// 徽章文案走 i18n（见 BankPreviewCard 的 KIND_LABEL）。

export type BankDiffKind = "add" | "dup" | "skip" | "hint";

export interface BankDiffRow {
  cells: string[];
  kind: BankDiffKind;
}

export interface BankDiffTable {
  header: string[];
  rows: BankDiffRow[];
}

const HEADER = ["题目", "领域", "科目", "来源"];

function splitCells(line: string): string[] | null {
  const text = line.trim();
  if (!text.startsWith("|") || !text.endsWith("|")) return null;
  return text
    .slice(1, -1)
    .split("|")
    .map((cell) => cell.trim());
}

function classify(origin: string): BankDiffKind | null {
  if (origin === "导入" || origin === "CSV 导入") return "add";
  if (origin.startsWith("已存在")) return "dup";
  // 「提示」先于「跳过」：提示正文里可能带"跳过"字样（如未知列名叫「跳过原因」），
  // 反过来判会把提示行染成红「跳过」徽章（C-2 审查 m1）
  if (origin.startsWith("提示")) return "hint";
  if (origin.startsWith("跳过") || origin.includes("跳过")) return "skip";
  return null;
}

/** 解析导入预览的差异表；不能确定性解析时返回 null（调用方回落 <pre>）。 */
export function parseImportDiff(diff: string[]): BankDiffTable | null {
  if (diff.length < 3) return null;
  const header = splitCells(diff[0]);
  if (!header || header.length !== HEADER.length) return null;
  if (header.some((cell, i) => cell !== HEADER[i])) return null;
  const separator = splitCells(diff[1]);
  if (!separator || separator.length !== HEADER.length) return null;
  if (!separator.every((cell) => /^-+$/.test(cell))) return null;
  const rows: BankDiffRow[] = [];
  for (const line of diff.slice(2)) {
    const cells = splitCells(line);
    if (!cells || cells.length !== HEADER.length) return null;
    const kind = classify(cells[3]);
    if (!kind) return null;
    rows.push({ cells, kind });
  }
  return { header, rows };
}
