import { describe, expect, it } from "vitest";

import {
  MANUAL_PROVIDER_ID,
  domainOf,
  matchProvider,
  presetDraft,
  type MailProvider,
} from "../../src/lib/mailProviders";

const QQ: MailProvider = {
  id: "qq",
  labelKey: "mailProvider.qq",
  domains: ["qq.com", "foxmail.com"],
  host: "imap.qq.com",
  port: 993,
  requiresAppPassword: true,
  authHintKey: "mailProvider.hintQq",
  docUrl: "",
  imapIdRequired: false,
  unsupported: false,
};

const NETEASE: MailProvider = {
  id: "netease163",
  labelKey: "mailProvider.netease163",
  domains: ["163.com"],
  host: "imap.163.com",
  port: 993,
  requiresAppPassword: true,
  authHintKey: "mailProvider.hintNetease",
  docUrl: "",
  imapIdRequired: true,
  unsupported: false,
};

const PROVIDERS = [QQ, NETEASE];

describe("domainOf", () => {
  it("取最后一段 @ 之后的内容并转小写", () => {
    expect(domainOf("user@" + "qq.com")).toBe("qq.com");
    expect(domainOf("user@" + "GMAIL.COM")).toBe("gmail.com");
    expect(domainOf("weird@sub@" + "qq.com")).toBe("qq.com");
  });

  it("不是邮箱形状时返回空串（调用方据此安静地不提示）", () => {
    expect(domainOf("")).toBe("");
    expect(domainOf("not-an-email")).toBe("");
    expect(domainOf("@")).toBe("");
  });
});

describe("matchProvider", () => {
  it("按域名命中预设", () => {
    expect(matchProvider("user@" + "qq.com", PROVIDERS)?.id).toBe("qq");
    expect(matchProvider("user@" + "163.com", PROVIDERS)?.id).toBe("netease163");
  });

  it("未知域名返回 null", () => {
    expect(matchProvider("a@some-corp.example", PROVIDERS)).toBeNull();
  });

  it("不做后缀匹配：evil-qq.com 不是 QQ 邮箱", () => {
    expect(matchProvider("user@" + "not-qq.com", PROVIDERS)).toBeNull();
  });

  it("空输入不炸（未填邮箱时也要能渲染整张卡）", () => {
    expect(matchProvider("", PROVIDERS)).toBeNull();
  });

  it("预设清单为空（后端未就绪）时也返回 null", () => {
    expect(matchProvider("user@" + "qq.com", [])).toBeNull();
  });
});

describe("presetDraft", () => {
  const current = { host: "imap.old.example", port: "143" };

  it("未改动过时，选服务商即带出它的服务器与端口", () => {
    expect(presetDraft(QQ, current, false)).toEqual({ host: "imap.qq.com", port: "993" });
  });

  it("用户手改过之后不再覆写（静默覆盖是最难察觉的一类 bug）", () => {
    expect(presetDraft(QQ, current, true)).toEqual(current);
  });

  it("选「其它（手工填写）」时不动任何字段", () => {
    expect(presetDraft(null, current, false)).toEqual(current);
  });

  it("端口以字符串形式给出（受控 input 的值类型）", () => {
    expect(typeof presetDraft(NETEASE, current, false).port).toBe("string");
  });
});

describe("MANUAL_PROVIDER_ID", () => {
  it("不与任何真实预设 id 撞车（它是下拉里的哨兵项）", () => {
    expect(PROVIDERS.map((p) => p.id)).not.toContain(MANUAL_PROVIDER_ID);
  });
});
