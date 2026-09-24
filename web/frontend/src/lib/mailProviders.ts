// 邮箱服务商预设的**纯判定**（无 I/O、无 i18n、无 http）——单测不需要 jsdom。
//
// 预设表本身**不在这里**：真源是后端的 `jobws_core/mail_providers.py`，经
// `GET /api/mail/providers` 下发（客户端见 lib/mailSetupApi.ts）。前端再复制一份
// 表迟早与后端漂移——「163 要不要先发 IMAP ID」这种事只该有一处说了算。
//
// 这一层只回答三件事：邮箱属于哪个服务商、选服务商时该不该覆写服务器字段、
// 以及下拉里那个「其它（手工填写）」哨兵怎么表示。

export interface MailProvider {
  id: string;
  labelKey: string;
  domains: string[];
  host: string;
  port: number;
  /** true = 网页登录密码一定失败，必须用授权码 / 应用专用密码 */
  requiresAppPassword: boolean;
  /** 「怎么拿授权码」的文案 key */
  authHintKey: string;
  /** 官方开启指引；后端没核实过的会留空串 */
  docUrl: string;
  /** true = 必须在 SELECT 之前发 IMAP ID（163 / 126 / yeah.net） */
  imapIdRequired: boolean;
  /** 已知在当前实现下不可用（Outlook 个人账号基本认证已停用） */
  unsupported: boolean;
  unsupportedReasonKey?: string;
}

/** 下拉里的「其它（手工填写）」：选中它不覆写任何字段。 */
export const MANUAL_PROVIDER_ID = "manual";

export interface ImapEndpoint {
  host: string;
  port: string;
}

/** 取邮箱域名（小写）；不是邮箱形状时返回空串。 */
export function domainOf(email: string): string {
  const at = (email ?? "").lastIndexOf("@");
  if (at < 0) return "";
  return email.slice(at + 1).trim().toLowerCase();
}

/**
 * 按域名**精确**匹配预设；未知域名或清单未就绪时返回 null。
 *
 * 精确匹配是刻意的：`not-qq.com` 不该被当成 QQ 邮箱——把服务器地址交给一个
 * "看起来像"的域名，等于把授权码送错地方。
 */
export function matchProvider(
  email: string,
  providers: MailProvider[]
): MailProvider | null {
  const domain = domainOf(email);
  if (!domain) return null;
  const hit = (providers ?? []).find((provider) =>
    provider.domains.includes(domain)
  );
  return hit ?? null;
}

/**
 * 选服务商后带出的服务器 / 端口。
 *
 * `dirty` = 用户已经手改过这两个字段；一旦 dirty 就不覆写——把用户刚敲进去的地址
 * 静默换掉是这类"智能填充"最容易被骂的地方（而且改回去要重敲一遍）。
 * `provider` 为 null（「其它」）时同样什么都不动。
 */
export function presetDraft(
  provider: MailProvider | null,
  current: ImapEndpoint,
  dirty: boolean
): ImapEndpoint {
  if (!provider || dirty) return current;
  return { host: provider.host, port: String(provider.port) };
}
