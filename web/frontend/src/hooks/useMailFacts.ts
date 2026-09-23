import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Application, type ImapMessage, type Mail } from "../api";
import type { MailFact } from "../lib/domainTypes";
import { planFactWrite } from "../lib/factWrites";
import { suggestFacts, suggestFactsAi } from "../lib/mailFacts";

/**
 * 邮件候选事实的状态与动作（批 9）：拉取事实、逐条写入、可选 AI 增强。
 *
 * 抽成 hook 的两个理由：
 * 1. 组件只剩渲染（`MailSuggestions.tsx` 回到规模预算内）；
 * 2. 写入路径集中一处、一眼看完——三条既有链路 + 阶段的两段式（先取原阶段再写），
 *    新增写通道时这里必然要改，审查者不必在 JSX 里找。
 */
export function useMailFacts(message: ImapMessage) {
  const { t } = useTranslation();
  const [facts, setFacts] = useState<MailFact[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [done, setDone] = useState<Record<string, string>>({});
  const [ignored, setIgnored] = useState<Record<string, boolean>>({});
  const [acked, setAcked] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState<string | null>(null);
  // 可选 AI 增强：只在 Provider 已配置（BYOK）时出现；模型名由用户填并记住
  const [providerReady, setProviderReady] = useState(false);
  const [model, setModel] = useState(() => {
    try {
      return localStorage.getItem("jobws_ai_model") || "";
    } catch {
      return "";
    }
  });
  const [aiBusy, setAiBusy] = useState(false);
  const [aiModel, setAiModel] = useState("");

  useEffect(() => {
    let alive = true;
    setFacts(null);
    setDone({});
    setIgnored({});
    setAcked({});
    suggestFacts({ 原文: message.body || "", ics: message.calendar || "" })
      .then((r) => {
        if (alive) setFacts(r.facts);
      })
      .catch((e: Error) => {
        if (alive) setError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [message.uid, message.body, message.calendar]);

  useEffect(() => {
    api
      .getProvider()
      .then((p) => setProviderReady(!!p.hasKey))
      .catch(() => setProviderReady(false));
  }, []);

  const keyOf = useCallback(
    (fact: MailFact, index: number) => `${fact.kind}:${fact.value}:${index}`,
    []
  );

  const write = useCallback(
    async (fact: MailFact, index: number): Promise<boolean> => {
      const plan = planFactWrite(fact, message);
      if (plan.kind === "blocked") {
        setError(t(plan.reasonKey));
        return false;
      }
      const key = keyOf(fact, index);
      setBusy(key);
      setError(null);
      try {
        if (plan.kind === "mail") {
          await api.createMail(plan.body as Partial<Mail>);
        } else if (plan.kind === "application") {
          await api.updateApplication(plan.id, plan.body as Partial<Application>);
        } else {
          // 阶段：先用既有只读接口取「原阶段」——服务端据此判断建议是否已过期，
          // 覆盖规则（终态不回退 / 拒信不覆盖 offer）也在服务端算，这里只做呈现。
          const result = await api.suggestStatus(message.body || "", plan.id);
          const match = result.matches.find((m) => m.id === plan.id);
          if (!match) throw new Error(t("suggest.recordGone"));
          if (!match.可覆盖) throw new Error(match.原因 || t("suggest.notAllowed"));
          await api.applyStatusSuggestion({
            id: plan.id,
            阶段: plan.stage,
            原阶段: match.当前阶段,
            依据: plan.evidence || undefined,
          });
        }
        setDone((prev) => ({ ...prev, [key]: t("suggest.done") }));
        return true;
      } catch (e) {
        setError((e as Error).message);
        return false;
      } finally {
        setBusy(null);
      }
    },
    [keyOf, message, t]
  );

  const runAi = useCallback(async () => {
    const name = model.trim();
    if (!name) {
      setError(t("suggest.aiNeedModel"));
      return;
    }
    setAiBusy(true);
    setError(null);
    try {
      const result = await suggestFactsAi({
        原文: message.body || "",
        ics: message.calendar || "",
        model: name,
      });
      try {
        localStorage.setItem("jobws_ai_model", name);
      } catch {
        /* 存储不可用：本次照常，下次重填 */
      }
      setFacts((prev) => {
        const existing = prev ?? [];
        const seen = new Set(existing.map((f) => `${f.kind}:${f.value}`));
        return [...existing, ...result.facts.filter((f) => !seen.has(`${f.kind}:${f.value}`))];
      });
      setAiModel(result.model);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  }, [message, model, t]);

  const copy = useCallback(
    (fact: MailFact, index: number) => {
      if (!navigator.clipboard?.writeText) return;
      const key = keyOf(fact, index);
      navigator.clipboard
        .writeText(fact.value)
        .then(() => {
          setCopied(key);
          setTimeout(() => setCopied(null), 1500);
        })
        .catch(() => {
          /* 剪贴板不可用时静默：链接本身可选中复制 */
        });
    },
    [keyOf]
  );

  const setAck = useCallback((key: string, value: boolean) => {
    setAcked((prev) => ({ ...prev, [key]: value }));
  }, []);

  const ignore = useCallback((key: string) => {
    setIgnored((prev) => ({ ...prev, [key]: true }));
  }, []);

  return {
    facts, error, setError, busy, done, ignored, acked, copied,
    providerReady, model, setModel, aiBusy, aiModel,
    keyOf, write, runAi, copy, setAck, ignore,
  };
}
