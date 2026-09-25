import { describe, expect, it } from "vitest";

import { planFactWrite } from "../../src/lib/factWrites";
import type { MailFact } from "../../src/lib/domainTypes";

/**
 * 「确认写入」的动作规划（批 9）：把一条候选事实翻译成**既有写路径**的调用。
 *
 * 三条纪律（与后端红线同源）：
 * 1. 每条事实只落一条既有链路——不新建写通道；
 * 2. 缺「对应记录」时说清楚原因（blocked），而不是悄悄写进错的记录；
 * 3. 低把握（confidence=low）不影响动作形态：把握程度只决定界面默认要不要勾选。
 */

const MESSAGE = {
  subject: "面试邀请（技术面）",
  from: "hr@example.com",
  date: "2026-09-20 10:00",
  messageId: "abc@example.com",
};

function fact(overrides: Partial<MailFact>): MailFact {
  return {
    kind: "会议链接",
    value: "https://meeting.tencent.com/dm/abc123",
    label: "会议链接",
    evidence: "链接：https://meeting.tencent.com/dm/abc123",
    confidence: "high",
    source: "ics",
    targetId: "",
    note: "",
    ...overrides,
  };
}

describe("planFactWrite", () => {
  it("时间 + 已知记录 → 写给投递记录的「下次动作日期」（只取日期部分）", () => {
    const plan = planFactWrite(
      fact({ kind: "时间", value: "2026-09-25 14:00", targetId: "A001" }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "application",
      id: "A001",
      body: { 下次动作日期: "2026-09-25" },
    });
  });

  it("时间但没匹配到记录 → blocked（不猜记录）", () => {
    const plan = planFactWrite(fact({ kind: "时间", value: "2026-09-25 14:00" }), MESSAGE);

    expect(plan).toEqual({ kind: "blocked", reasonKey: "suggest.needRecord" });
  });

  it("会议链接 → 记入邮件台账（带元数据与关联记录）", () => {
    const plan = planFactWrite(fact({ targetId: "A001" }), MESSAGE);

    expect(plan).toEqual({
      kind: "mail",
      body: {
        主题: MESSAGE.subject,
        发件人: MESSAGE.from,
        日期: MESSAGE.date,
        消息id: MESSAGE.messageId,
        关联记录: "A001",
        会议链接: "https://meeting.tencent.com/dm/abc123",
      },
    });
  });

  it("公司岗位 → 记入邮件台账并关联到该记录", () => {
    const plan = planFactWrite(
      fact({ kind: "公司岗位", value: "A007", label: "星河数据 · 热管理" }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "mail",
      body: {
        主题: MESSAGE.subject,
        发件人: MESSAGE.from,
        日期: MESSAGE.date,
        消息id: MESSAGE.messageId,
        关联记录: "A007",
      },
    });
  });

  it("阶段 → 走既有的两段式状态链路（原阶段由调用方在写前取得）", () => {
    const plan = planFactWrite(
      fact({ kind: "阶段", value: "一面", evidence: "邀请您参加一面", targetId: "A001" }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "status",
      id: "A001",
      stage: "一面",
      evidence: "邀请您参加一面",
    });
  });

  it("阶段但没有对应记录 → blocked", () => {
    const plan = planFactWrite(fact({ kind: "阶段", value: "一面" }), MESSAGE);

    expect(plan).toEqual({ kind: "blocked", reasonKey: "suggest.needRecord" });
  });

  it("把握程度不影响动作形态（low 走同一条链路）", () => {
    const plan = planFactWrite(
      fact({ kind: "时间", value: "2026-09-25", targetId: "A001", confidence: "low" }),
      MESSAGE
    );

    expect(plan.kind).toBe("application");
  });

  it("截止 → 同时写「下次动作日期」与「下次动作」文案（到点提醒读这两个字段）", () => {
    const plan = planFactWrite(
      fact({ kind: "截止", value: "2026-09-25", label: "完成在线测评", targetId: "A001" }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "application",
      id: "A001",
      body: { 下次动作日期: "2026-09-25", 下次动作: "完成在线测评" },
    });
  });

  it("截止带钟点 → 「下次动作日期」只取日期部分", () => {
    const plan = planFactWrite(
      fact({ kind: "截止", value: "2026-09-25 18:00", label: "完成笔试", targetId: "A007" }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "application",
      id: "A007",
      body: { 下次动作日期: "2026-09-25", 下次动作: "完成笔试" },
    });
  });

  it("截止但没匹配到记录 → blocked（不猜记录）", () => {
    const plan = planFactWrite(
      fact({ kind: "截止", value: "2026-09-25", label: "完成在线测评" }),
      MESSAGE
    );

    expect(plan).toEqual({ kind: "blocked", reasonKey: "suggest.needRecord" });
  });

  it("链接有效期 → 与截止同一条写路径（区别只在动作文案里）", () => {
    const plan = planFactWrite(
      fact({
        kind: "链接有效期",
        value: "2026-09-24",
        label: "完成测评（链接即将失效）",
        targetId: "A001",
      }),
      MESSAGE
    );

    expect(plan).toEqual({
      kind: "application",
      id: "A001",
      body: { 下次动作日期: "2026-09-24", 下次动作: "完成测评（链接即将失效）" },
    });
  });

  // 2026-09-25 真机缺陷：后端没匹配到记录时，用户在卡片上就地选定归属（PR-4）
  it("后端没给归属时，就地选定的记录补位（targetOverride）", () => {
    const plan = planFactWrite(
      fact({ kind: "链接有效期", value: "2026-09-24", label: "完成测评（链接即将失效）" }),
      MESSAGE,
      "A002"
    );

    expect(plan).toEqual({
      kind: "application",
      id: "A002",
      body: { 下次动作日期: "2026-09-24", 下次动作: "完成测评（链接即将失效）" },
    });
  });

  it("override 优先于后端匹配到的 targetId（用户显式选择说了算）", () => {
    const plan = planFactWrite(
      fact({ kind: "阶段", value: "一面", evidence: "邀请您参加一面", targetId: "A001" }),
      MESSAGE,
      "A002"
    );

    expect(plan.kind === "status" && plan.id).toBe("A002");
  });
});
