import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DRILL_KEY,
  PREPARE_TAB_KEY,
  PROGRESS_TAB_KEY,
  drillToJob,
  drillToTab,
} from "../../src/lib/pageDrill";

/**
 * 键名是「写方与读方各写一遍」的契约（写方 = pageDrill / Dashboard / ApplicationRow，
 * 读方 = 各页面自己的 DRILL_KEY）。这里把三个键的**字面值**钉死——谁改了常量，
 * 测试立刻报错，而不是让下钻静默落回默认页签（2026-09-22 审查 MINOR 笔 4）。
 */
function stubEnv() {
  const store = new Map<string, string>();
  const location = { hash: "" };
  vi.stubGlobal("sessionStorage", {
    setItem: (key: string, value: string) => void store.set(key, value),
    getItem: (key: string) => store.get(key) ?? null,
  });
  vi.stubGlobal("window", { location } as unknown as Window & typeof globalThis);
  return { store, location };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("pageDrill 键名契约", () => {
  it("三个键的字面值稳定", () => {
    expect(DRILL_KEY).toBe("jobws_drill");
    expect(PREPARE_TAB_KEY).toBe("jobws_prepare_tab");
    expect(PROGRESS_TAB_KEY).toBe("jobws_progress_tab");
  });

  it("drillToTab 写到给定的键并跳对应页面", () => {
    const { store, location } = stubEnv();

    drillToTab("prepare", PREPARE_TAB_KEY, "talks");

    expect(store.get(PREPARE_TAB_KEY)).toBe("talks");
    expect(location.hash).toBe("prepare");
  });

  it("drillToJob 用 DRILL_KEY 写 focusDir 并跳岗位池", () => {
    const { store, location } = stubEnv();

    drillToJob("云帆智算_后端");

    expect(JSON.parse(store.get(DRILL_KEY) ?? "{}")).toEqual({ focusDir: "云帆智算_后端" });
    expect(location.hash).toBe("jobs");
  });

  it("存储不可用时只跳页面、不抛错", () => {
    const location = { hash: "" };
    vi.stubGlobal("sessionStorage", {
      setItem: () => {
        throw new Error("quota");
      },
      getItem: () => null,
    });
    vi.stubGlobal("window", { location } as unknown as Window & typeof globalThis);

    expect(() => drillToTab("progress", PROGRESS_TAB_KEY, "offers")).not.toThrow();
    expect(location.hash).toBe("progress");
  });
});
