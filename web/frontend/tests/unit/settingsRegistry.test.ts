import { describe, expect, it, vi } from "vitest";

import {
  buildPreferenceEntries,
  filterEntries,
  matchesQuery,
  modifiedCardIds,
  type PreferenceSources,
  visibleCardIds,
} from "../../src/lib/settingsRegistry";

function sources(overrides: Partial<PreferenceSources> = {}): PreferenceSources {
  const stub = (value: string | number | boolean, def: string | number | boolean) => ({
    value,
    def,
    display: String(value),
    reset: vi.fn(),
  });
  return {
    theme: stub("system", "system"),
    font: stub("inter", "inter"),
    mono: stub("maple", "maple"),
    numeric: stub("geist-mono", "geist-mono"),
    fontSize: stub(100, 100),
    lang: stub("zh-CN", "zh-CN"),
    zoom: null,
    reminders: null,
    ...overrides,
  };
}

describe("buildPreferenceEntries", () => {
  it("全默认时没有任何一项算被改", () => {
    const entries = buildPreferenceEntries(sources());
    expect(entries.length).toBe(6);
    expect(entries.every((entry) => entry.modified === false)).toBe(true);
  });

  it("值与默认不同才算被改（逐项判，不是整组判）", () => {
    const entries = buildPreferenceEntries(
      sources({
        theme: { value: "nord", def: "system", display: "Nord", reset: vi.fn() },
        fontSize: { value: 120, def: 100, display: "120%", reset: vi.fn() },
      })
    );
    const byId = Object.fromEntries(entries.map((entry) => [entry.id, entry]));
    expect(byId.theme.modified).toBe(true);
    expect(byId.fontSize.modified).toBe(true);
    expect(byId.font.modified).toBe(false);
  });

  it("没有通道的项（浏览器里没有缩放 / 提醒）不出现在列表里，而不是显示成改了没用", () => {
    const entries = buildPreferenceEntries(sources());
    expect(entries.map((entry) => entry.id)).not.toContain("zoom");
    expect(entries.map((entry) => entry.id)).not.toContain("reminders");
  });

  it("桌面端有通道时缩放与提醒各自成项，且默认值来自真值源", () => {
    const entries = buildPreferenceEntries(
      sources({
        zoom: { value: 1, def: 0, display: "120%", reset: vi.fn() },
        reminders: { value: false, def: false, display: "off", reset: vi.fn() },
      })
    );
    const byId = Object.fromEntries(entries.map((entry) => [entry.id, entry]));
    expect(byId.zoom.modified).toBe(true);
    expect(byId.zoom.cardId).toBe("zoom");
    expect(byId.reminders.modified).toBe(false);
  });

  it("还原回调原样带出（登记表不替调用方做决定）", () => {
    const reset = vi.fn();
    const entries = buildPreferenceEntries(
      sources({ theme: { value: "nord", def: "system", display: "Nord", reset } })
    );
    const theme = entries.find((entry) => entry.id === "theme");
    theme?.reset?.();
    expect(reset).toHaveBeenCalledTimes(1);
  });
});

describe("modifiedCardIds / filterEntries", () => {
  it("只收被改过的项所在的卡（用于 @modified 过滤）", () => {
    const entries = buildPreferenceEntries(
      sources({
        lang: { value: "en", def: "zh-CN", display: "English", reset: vi.fn() },
        mono: { value: "jetbrains", def: "maple", display: "JetBrains", reset: vi.fn() },
      })
    );
    expect([...modifiedCardIds(entries)].sort()).toEqual(["lang", "theme"]);
  });

  it("按 id 过滤条目（搜索框里的文本会一路收窄到项）", () => {
    const entries = buildPreferenceEntries(sources());
    expect(filterEntries(entries, "font").map((entry) => entry.id)).toEqual([
      "font",
      "fontSize",
    ]);
  });
});

describe("matchesQuery", () => {
  it("空查询匹配全部", () => {
    expect(matchesQuery({ id: "theme" }, "")).toBe(true);
    expect(matchesQuery({ id: "theme" }, "   ")).toBe(true);
  });

  it("文本不区分大小写，命中 id 或任一关键词", () => {
    const subject = { id: "zoom", keywords: ["界面大小", "size"] };
    expect(matchesQuery(subject, "SIZE")).toBe(true);
    expect(matchesQuery(subject, "界面")).toBe(true);
    expect(matchesQuery(subject, "nope")).toBe(false);
  });

  it("@modified 只认被改过的对象，可与文本混用", () => {
    expect(matchesQuery({ id: "theme", modified: true }, "@modified")).toBe(true);
    expect(matchesQuery({ id: "theme", modified: false }, "@modified")).toBe(false);
    expect(matchesQuery({ id: "theme", modified: true }, "@modified theme")).toBe(true);
    expect(matchesQuery({ id: "theme", modified: true }, "@modified 다른")).toBe(false);
  });
});

describe("visibleCardIds", () => {
  it("不筛时所有卡可见", () => {
    expect(visibleCardIds("", "all").size).toBe(9);
  });

  it("分区筛选只留该分区的卡", () => {
    const ids = visibleCardIds("", "services");
    expect([...ids].sort()).toEqual(["imap", "provider"]);
  });

  it("文本命中卡片关键词（中英混搜都能命中）", () => {
    expect([...visibleCardIds("邮箱", "all")]).toEqual(["imap"]);
    expect([...visibleCardIds("snapshot", "all")]).toEqual(["privacy"]);
    expect(visibleCardIds("zzz", "all").size).toBe(0);
  });

  it("@modified 收窄到「有被改项」的卡，浏览器里改过主题就只剩主题与偏好两张卡", () => {
    const ids = visibleCardIds("@modified", "all", new Set(["theme", "prefs"]));
    expect([...ids].sort()).toEqual(["prefs", "theme"]);
    expect(visibleCardIds("@modified", "all").size).toBe(0);
  });

  it("分区与 @modified 同时生效（先分区、再收窄）", () => {
    const ids = visibleCardIds("@modified", "data", new Set(["theme", "privacy"]));
    expect([...ids]).toEqual(["privacy"]);
  });
});
