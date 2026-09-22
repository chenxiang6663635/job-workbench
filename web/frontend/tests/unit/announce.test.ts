import { afterEach, describe, expect, it, vi } from "vitest";
import { ANNOUNCE_EVENT, announce } from "../../src/lib/announce";

/**
 * UX-6 的发送端守卫：播报是「读屏用户唯一能听到成功」的通道，派发契约（事件名、
 * detail 载荷）一旦漂移，调用方全都静默失效——而这种失效在 UI 上看不出来。
 * 接收端的 trim / 同句重播由 LiveRegion 负责，这里的职责只到"原样派发"。
 */
function stubWindow() {
  const listeners: Record<string, ((event: Event) => void)[]> = {};
  return {
    listeners,
    addEventListener: (type: string, cb: (event: Event) => void) => {
      (listeners[type] ||= []).push(cb);
    },
    removeEventListener: (type: string, cb: (event: Event) => void) => {
      listeners[type] = (listeners[type] || []).filter((fn) => fn !== cb);
    },
    dispatchEvent: (event: Event) => {
      (listeners[event.type] || []).forEach((cb) => cb(event));
      return true;
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("announce（成功播报）", () => {
  it("带上载荷派发 announce 事件：接收端能原样取回文案", () => {
    const target = stubWindow();
    vi.stubGlobal("window", target);
    const received: string[] = [];
    const listener = (event: Event) => received.push((event as CustomEvent).detail);
    target.addEventListener(ANNOUNCE_EVENT, listener);

    announce("Application created: 云帆智算 后端");

    expect(received).toEqual(["Application created: 云帆智算 后端"]);
  });

  it("同名事件不会串到别的自定义事件上：事件名固定且在 twice 调用后可注销", () => {
    const target = stubWindow();
    vi.stubGlobal("window", target);
    const seen: string[] = [];
    const listener = (event: Event) => seen.push((event as CustomEvent).detail);

    target.addEventListener(ANNOUNCE_EVENT, listener);
    announce("first");
    announce("second");
    target.removeEventListener(ANNOUNCE_EVENT, listener);
    announce("third");

    expect(seen).toEqual(["first", "second"]);
    // 事件名恰好等于它自己：把"改了 announce 忘了改 LiveRegion"这条漂移钉死
    expect(ANNOUNCE_EVENT).toBe("jobws:announce");
  });
});
