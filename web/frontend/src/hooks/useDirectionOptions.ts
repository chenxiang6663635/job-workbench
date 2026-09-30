import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { buildDirectionOptions, type DirectionOption } from "../lib/directionOptions";
import { domainLabel } from "../lib/domainLabels";
import { requestJson } from "../lib/http";

// 方向候选的拉取与合成（GET /api/workspaces/directions，2026-09-30）。
//
// 为什么直连 `lib/http` 而不进 `api.ts`：`api.ts` 在规模闸门的水位上、且“只许变小”，
// 而 `lib/http` 本就是窄模块的正门（drill / records 同款）——这条注释就是它的端点
// 清单入口。
//
// 拉不到（后端没起、或老后端没有这个端点）就退化成空表：下拉只剩「记录里已用过的值」，
// 界面照常可用——候选动态化不该新增任何“打不开页面”的路径。
interface DirectionsPayload {
  items: { id: string; title: string }[];
  alwaysAccepted: string[];
}

const EMPTY: DirectionsPayload = { items: [], alwaysAccepted: [] };

export function useDirectionOptions(used: string[] = []): DirectionOption[] {
  const { t } = useTranslation();
  const [data, setData] = useState<DirectionsPayload>(EMPTY);

  useEffect(() => {
    let alive = true;   // 卸载后不再 setState（StrictMode 下也不会写回过期结果）
    requestJson<DirectionsPayload>("/workspaces/directions").then(
      (body) => {
        if (!alive) return;
        setData({
          items: Array.isArray(body?.items) ? body.items : [],
          alwaysAccepted: Array.isArray(body?.alwaysAccepted) ? body.alwaysAccepted : [],
        });
      },
      () => {
        if (alive) setData(EMPTY);
      }
    );
    return () => {
      alive = false;
    };
  }, []);

  // 调用方多半就地 map 出新数组（如 `rows.map((r) => r.方向)`）：按**内容**而不是
  // 数组引用做依赖，免得每次渲染都重算候选。键用 JSON 序列化——用分隔符连接的话，
  // 值里恰好含该分隔符会串味（["a\u0000b"] 与 ["a","b"] 撞成同一个键）。
  const usedKey = JSON.stringify(used);
  const usedValues = useMemo(
    () => (usedKey === "[]" ? [] : (JSON.parse(usedKey) as string[])),
    [usedKey]
  );

  return useMemo(
    () =>
      buildDirectionOptions({
        ...data,
        used: usedValues,
        fallbackLabel: (value) => domainLabel("direction", value, t),
      }),
    [data, usedValues, t]
  );
}
