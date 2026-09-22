import { beforeEach, describe, expect, it, vi } from "vitest";
import { humanizeError, requestJson, setWorkspace } from "../../src/lib/http";

/**
 * H-1 批（前端 HTTP 单一实现）的守卫网：此前 request / humanize / ws 自检在
 * api.ts 与 lib/bank.ts / lib/drill.ts / lib/records.ts 各抄了一份——这里把
 * 「错误本地化」「422 数组拼接」「ws 参数拼接」「工作区自检」四个行为钉住，
 * 收敛后四处共用同一实现，改这里就是改全站。
 *
 * i18n 在 node 环境下初始化会碰 document / localStorage（src/i18n/index.ts），
 * 这里 mock 成最小替身：本文件测的是 http.ts 的分支逻辑，语言包文案由
 * err.<code> 键的中英成对契约测试负责（Python 侧 test_error_code_params）。
 */
const mocks = vi.hoisted(() => ({
  exists: vi.fn((key: string) => key === "err.prep.missingLines"),
  t: vi.fn((key: string) => `【${key}】`),
}));
vi.mock("../../src/i18n", () => ({
  default: { exists: mocks.exists, t: mocks.t },
}));

const okResponse = (body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status: 200, headers });

beforeEach(() => {
  mocks.exists.mockClear();
  mocks.t.mockClear();
  setWorkspace("");
  vi.unstubAllGlobals();
});

describe("humanizeError（错误本地化）", () => {
  it("error_code 命中语言包：用本地化文案，params 全部转成字符串", () => {
    const msg = humanizeError(
      JSON.stringify({ error_code: "prep.missingLines", error_params: { lines: 3 } }),
      400
    );
    expect(msg).toBe("【err.prep.missingLines】");
    const call = mocks.t.mock.calls.find(([key]) => key === "err.prep.missingLines");
    expect(call?.[1]).toEqual({ lines: "3" });
  });

  it("error_code 查不到：回落 detail 原文（绝不把 err.xxx 这个 key 名显示给用户）", () => {
    expect(
      humanizeError(JSON.stringify({ error_code: "nope.nope", detail: "详情" }), 400)
    ).toBe("详情");
  });

  it("422 数组 detail 逐条拼接：带字段路径、跳过 loc[0] 的 body、空数组回落原文", () => {
    const msg = humanizeError(
      JSON.stringify({
        detail: [
          { loc: ["body", "title"], msg: "不能为空" },
          { msg: "格式错" },
        ],
      }),
      422
    );
    expect(msg).toBe("title: 不能为空；格式错");
  });

  it("非 JSON 原文返回；超长截断到 300 字符", () => {
    expect(humanizeError("plain text", 500)).toBe("plain text");
    expect(humanizeError("x".repeat(400), 500)).toBe(`${"x".repeat(300)}…`);
  });

  it("空 body 用 requestFailed 兜底并带上 status", () => {
    const msg = humanizeError("   ", 502);
    expect(msg).toBe("【api.requestFailed】");
    expect(mocks.t).toHaveBeenCalledWith("api.requestFailed", { status: 502 });
  });
});

describe("requestJson（请求 + 工作区自检）", () => {
  it("成功：解析 JSON；未选工作区时不带 ws 参数", async () => {
    const fetchMock = vi.fn(async () => okResponse({ ok: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(requestJson<{ ok: number }>("/dashboard")).resolves.toEqual({ ok: 1 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/dashboard");
  });

  it("已选工作区：追加 ws 参数（已有 query 用 &；setWorkspace 立即生效）", async () => {
    const fetchMock = vi.fn(async () => okResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    setWorkspace("personal");
    await requestJson("/dashboard");
    await requestJson("/x?a=1");
    await requestJson("/book 名?q=中 文");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/dashboard?ws=personal");
    expect(fetchMock.mock.calls[1][0]).toBe("/api/x?a=1&ws=personal");
    expect(fetchMock.mock.calls[2][0]).toBe(
      `/api/book 名?q=中 文&ws=${encodeURIComponent("personal")}`
    );
  });

  it("POST：body 序列化、带 Content-Type；GET 不带 body 头", async () => {
    const fetchMock = vi.fn(async () => okResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    await requestJson("/applications", { method: "POST", body: { 公司: "A" } });
    await requestJson("/dashboard");
    const post = fetchMock.mock.calls[0][1] as RequestInit;
    expect(post.method).toBe("POST");
    expect(post.body).toBe(JSON.stringify({ 公司: "A" }));
    expect(post.headers).toEqual({ "Content-Type": "application/json" });
    const get = fetchMock.mock.calls[1][1] as RequestInit;
    expect(get.method).toBe("GET");
    expect(get.body).toBeUndefined();
  });

  it("!ok：抛 humanize 后的错误（含错误码本地化）", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "没有这条记录" }), { status: 404 })
      )
    );
    await expect(requestJson("/x")).rejects.toThrow("没有这条记录");
  });

  it("工作区自检：回显不一致 → 抛 workspaceMismatch（带 requested/served）", async () => {
    setWorkspace("personal");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => okResponse({}, { "X-Jobws-Workspace": "other" }))
    );
    await expect(requestJson("/x")).rejects.toThrow("【api.workspaceMismatch】");
    expect(mocks.t).toHaveBeenCalledWith("api.workspaceMismatch", {
      requested: "personal",
      served: "other",
    });
  });

  it("工作区自检：两端都有值才比较——缺头不误报、未选工作区不比较", async () => {
    const fetchMock = vi.fn(async () => okResponse({ done: true }));
    vi.stubGlobal("fetch", fetchMock);
    setWorkspace("personal");
    await expect(requestJson("/a")).resolves.toEqual({ done: true }); // 缺头
    setWorkspace("");
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => okResponse({ done: true }, { "X-Jobws-Workspace": "other" }))
    );
    await expect(requestJson("/b")).resolves.toEqual({ done: true }); // 未选工作区
  });
});
