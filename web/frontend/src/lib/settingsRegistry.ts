// 设置页的**登记表与纯判定**（首发前收口批 笔 4）。
//
// 设置页此前的三个问题都不是"少画了几个控件"：
//   1. **找得到**：九张卡只能靠滚动找，没有搜索、没有分区；
//   2. **退得回**：改过什么说不清，也没有单项还原（一年后只能"清 localStorage"）；
//   3. **改完知道会发生什么**：生效方式（即时 / 需保存）散落在各处，改了没反应时无法自证。
//
// 所以这里先建一张登记表：卡片属于哪个分组、有哪些搜索词；偏好项叫什么、属于哪张卡、
// 怎么算"被改过"、怎么退回去、什么时候生效。判定全部是纯函数——它决定"哪些卡可见、
// 哪些项算改过"，是可以被单测钉住的那一层（真正的读写仍由调用方注入，见 PreferenceSources）。

export type SettingsGroupId = "appearance" | "interface" | "services" | "data";

/** 生效方式：即时（改了就生效）/ 需保存（要按保存按钮）/ 需重启。 */
export type SettingsEffect = "instant" | "save" | "restart";

export interface SettingsGroup {
  id: SettingsGroupId;
  labelKey: string;
}

export const SETTINGS_GROUPS: SettingsGroup[] = [
  { id: "appearance", labelKey: "settings.groupAppearance" },
  { id: "interface", labelKey: "settings.groupInterface" },
  { id: "services", labelKey: "settings.groupServices" },
  { id: "data", labelKey: "settings.groupData" },
];

export interface SettingsCardMeta {
  id: string;
  group: SettingsGroupId;
  /** 搜索词：中英混合（界面语言会变，但用户可能用任一语言去搜） */
  keywords: string[];
}

/** 卡片的单一清单：`visibleCardIds` 与设置页渲染顺序都以它为准。 */
export const SETTINGS_CARDS: SettingsCardMeta[] = [
  { id: "lang", group: "interface", keywords: ["language", "界面语言", "语言", "english"] },
  { id: "theme", group: "appearance", keywords: ["theme", "主题", "外观", "字体", "font", "字号"] },
  { id: "zoom", group: "interface", keywords: ["zoom", "界面大小", "缩放", "size"] },
  { id: "provider", group: "services", keywords: ["provider", "模型", "api key", "密钥", "deepseek"] },
  { id: "imap", group: "services", keywords: ["imap", "邮箱", "mail", "授权码"] },
  { id: "prefs", group: "appearance", keywords: ["偏好", "preference", "已修改", "还原", "reset"] },
  { id: "dataLoc", group: "data", keywords: ["数据位置", "路径", "data", "portable", "便携"] },
  { id: "about", group: "data", keywords: ["关于", "about", "版本", "version"] },
  { id: "privacy", group: "data", keywords: ["隐私", "privacy", "备份", "快照", "snapshot", "诊断", "导出"] },
];

export interface SettingsEntry {
  /** 稳定 id：i18n 键、搜索与测试都用它 */
  id: string;
  labelKey: string;
  /** 属于哪张卡（`@modified` 过滤用它决定哪些卡可见） */
  cardId: string;
  effect: SettingsEffect;
  modified: boolean;
  /** 当前值的可读文本（调用方给，例如 "Maple Mono" / "120%" / "中文"） */
  value: string;
  /** 缺少回退路径的项不给按钮（例如只在桌面端存在的通道） */
  reset: (() => void) | null;
  /** 布尔项的开关（目前只有"到点提醒"）：给了就在卡片上渲染成开关而不是只读值 */
  toggle?: { on: boolean; set: (next: boolean) => void } | null;
}

/** 偏好的真值源（由调用方注入——这一层刻意不碰 localStorage / IPC，才谈得上单测）。 */
export interface PreferenceSources {
  theme: { value: string; def: string; display: string; reset: () => void };
  font: { value: string; def: string; display: string; reset: () => void };
  mono: { value: string; def: string; display: string; reset: () => void };
  numeric: { value: string; def: string; display: string; reset: () => void };
  fontSize: { value: number; def: number; display: string; reset: () => void };
  lang: { value: string; def: string; display: string; reset: () => void };
  /** 桌面端才有通道；浏览器里给 null（那一项直接不出现在列表里，而不是显示成"改了没用"） */
  zoom: { value: number; def: number; display: string; reset: () => void } | null;
  reminders:
    | {
        value: boolean;
        def: boolean;
        display: string;
        reset: () => void;
        set: (next: boolean) => void;
      }
    | null;
}

/** 登记表 → 渲染用的条目（顺序即展示顺序：外观 → 界面 → 提醒）。 */
export function buildPreferenceEntries(sources: PreferenceSources): SettingsEntry[] {
  const make = (
    id: string,
    cardId: string,
    labelKey: string,
    effect: SettingsEffect,
    source: { value: unknown; def: unknown; display: string; reset: () => void },
    toggle?: { on: boolean; set: (next: boolean) => void }
  ): SettingsEntry => ({
    id,
    cardId,
    labelKey,
    effect,
    modified: source.value !== source.def,
    value: source.display,
    reset: source.reset,
    toggle: toggle ?? null,
  });

  const entries: SettingsEntry[] = [
    make("theme", "theme", "settings.entryTheme", "instant", sources.theme),
    make("font", "theme", "settings.entryFont", "instant", sources.font),
    make("mono", "theme", "settings.entryMono", "instant", sources.mono),
    make("numeric", "theme", "settings.entryNumeric", "instant", sources.numeric),
    make("fontSize", "theme", "settings.entryFontSize", "instant", sources.fontSize),
    make("lang", "lang", "settings.entryLang", "instant", sources.lang),
  ];
  if (sources.zoom) entries.push(make("zoom", "zoom", "settings.entryZoom", "instant", sources.zoom));
  if (sources.reminders) {
    entries.push(
      make("reminders", "zoom", "settings.entryReminders", "instant", sources.reminders, {
        on: sources.reminders.value,
        set: sources.reminders.set,
      })
    );
  }
  return entries;
}

export function modifiedCount(entries: SettingsEntry[]): number {
  return entries.filter((entry) => entry.modified).length;
}

/** 被改过的项落在哪些卡上——`@modified` 过滤用它收窄可见卡片。 */
export function modifiedCardIds(entries: SettingsEntry[]): Set<string> {
  return new Set(entries.filter((entry) => entry.modified).map((entry) => entry.cardId));
}

/**
 * 搜索判定。
 *
 * 支持一个结构化记号 `@modified`（照 VS Code 的做法，只取最小集）：单独用 = 只看被改过的，
 * 与文本混用 = 两个条件同时满足。文本匹配不区分大小写，命中 id 或任一关键词即可。
 */
export function matchesQuery(
  subject: { id: string; keywords?: string[]; modified?: boolean },
  query: string
): boolean {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const haystack = [subject.id, ...(subject.keywords ?? [])].join(" ").toLowerCase();
  return tokens.every((token) =>
    token === "@modified" ? subject.modified === true : haystack.includes(token)
  );
}

export function filterEntries(entries: SettingsEntry[], query: string): SettingsEntry[] {
  return entries.filter((entry) => {
    const label = entry.labelKey.replace(/^settings\./, "");
    return matchesQuery({ id: entry.id, keywords: [label], modified: entry.modified }, query);
  });
}

/**
 * 哪些卡片该显示：`group` 先筛分区，`query` 再筛文字与 `@modified`。
 *
 * `@modified` 是特例：它描述的不是卡片本身而是卡片里的项，所以由调用方把
 * "有被改项的卡片集合"传进来（见 `modifiedCardIds`）。
 */
export function visibleCardIds(
  query: string,
  group: SettingsGroupId | "all",
  modifiedCards: Set<string> = new Set()
): Set<string> {
  const inGroup = SETTINGS_CARDS.filter((card) => group === "all" || card.group === group);
  const visible = inGroup.filter((card) => {
    const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
    const textTokens = tokens.filter((token) => token !== "@modified");
    const wantsModified = tokens.includes("@modified");
    if (wantsModified && !modifiedCards.has(card.id)) return false;
    if (textTokens.length === 0) return true;
    const haystack = [card.id, ...card.keywords].join(" ").toLowerCase();
    return textTokens.every((token) => haystack.includes(token));
  });
  return new Set(visible.map((card) => card.id));
}
