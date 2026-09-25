import { useCallback, useEffect, useState } from "react";

import { getProviderSettings } from "../lib/providerApi";

/**
 * 默认模型的单一入口（简历导入 / 简历改写 / 邮件 AI 三处共用）。
 *
 * 为什么要有它：同一个 provider、同一个模型名，原来要在三处各填一遍（其中两处还
 * 各自存 localStorage）——抄三处必然有两处不一致，出问题时也看不出用的是哪个。
 *
 * 为什么仍保留"临时改"：改写偶尔要换更强的模型，但那是**一次性的决定**，不该顺手
 * 改掉全局默认。所以覆盖只落在 localStorage（**本机持久**，不是会话级——下次打开
 * 还在），不写回 provider.json：写回等于"临时改一次变成永久改"，没人会预期这个。
 *
 * 已知张力：localStorage 覆盖**优先于**设置页默认，所以设置页后来改了默认模型，
 * 本处的旧覆盖仍会盖住它（用户在设置页看不到生效）。当前保留这个行为（"我上次
 * 选的"通常仍是想要的），但界面必须把来源说出来——见 `RewritePanel` 的提示行。
 *
 * 取值优先级：本次覆盖 > 设置页的默认模型 > 空（调用方继续要求手填）。
 */
export function useModelChoice(storageKey: string) {
  const [fallback, setFallback] = useState("");
  const [override, setOverride] = useState(() => readOverride(storageKey));

  useEffect(() => {
    let alive = true;
    getProviderSettings()
      .then((settings) => {
        if (alive) setFallback(settings.model);
      })
      .catch((e: Error) => {
        // 读不到默认模型不是错误：三处使用点各自会退回"手填"
        console.error("readProviderModel failed", e);
      });
    return () => {
      alive = false;
    };
  }, []);

  const setModel = useCallback(
    (next: string) => {
      setOverride(next);
      writeOverride(storageKey, next);
    },
    [storageKey]
  );

  return { model: override || fallback, setModel, defaultModel: fallback };
}

function readOverride(storageKey: string): string {
  try {
    return localStorage.getItem(storageKey) ?? "";
  } catch {
    return "";
  }
}

function writeOverride(storageKey: string, value: string): void {
  try {
    localStorage.setItem(storageKey, value);
  } catch {
    // localStorage 不可用不阻塞（隐私模式）
  }
}
