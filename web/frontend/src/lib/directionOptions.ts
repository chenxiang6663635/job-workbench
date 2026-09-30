// 方向候选的合成（纯函数，**不 import lib/http**——vitest 无 jsdom 才跑得起来）。
//
// 候选口径（2026-09-30 定）：**工作区实际装入的方向** ∪ **后端恒接受的取值** ∪
// **记录里已经用过的值**。三段缺一不可：
//   · 少了「装入的」→ 插件提供的方向选不到（此前长期只有写死的三项）；
//   · 少了「恒接受的」→ 连"其他方向"都没得选；
//   · 少了「已用过的」→ 换了插件之后，老记录的值不在候选里，Radix Select 会显示成
//     空、一提交就把值**静默改掉**（这正是本仓库反复防的那类静默错位）。
// 显示名：有标题就 `标题（原始值）`——看得懂，又能对上 CSV 里的值（中英界面同一套，
// 见 PR 决策）；没有标题时由调用方给兜底文案（既有 i18n 键），仍无则原样显示原始值。
export interface DirectionItem {
  id: string;
  title: string;
}

export interface DirectionOption {
  value: string;
  label: string;
}

export function buildDirectionOptions(input: {
  items: DirectionItem[];
  alwaysAccepted: string[];
  used: string[];
  fallbackLabel?: (value: string) => string;
}): DirectionOption[] {
  const seen = new Set<string>();
  const options: DirectionOption[] = [];
  const add = (raw: string, title?: string) => {
    const value = (raw || "").trim();
    if (!value || seen.has(value)) return;
    seen.add(value);
    const name = (title || "").trim();
    const fallback = input.fallbackLabel ? input.fallbackLabel(value) : value;
    options.push({ value, label: name ? `${name}（${value}）` : fallback });
  };
  for (const item of input.items) add(item.id, item.title);
  for (const value of input.alwaysAccepted) add(value);
  for (const value of input.used) add(value);
  return options;
}
