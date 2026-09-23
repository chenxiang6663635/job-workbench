import { useRef } from "react";

/**
 * 请求序号守卫：同一份数据的多次请求可能**乱序返回**，后到的旧响应会把新数据盖掉
 * （连续改两行的标签、连点两次「顺延 7 天」都会命中）。写法与 `Jobs` / `Applications`
 * 里那份守卫同源，只是收敛成一处，免得每加一个列表就再造一遍。
 *
 * 用法：
 * ```tsx
 * const seq = useSeq();
 * const load = () => {
 *   const n = seq.next();
 *   api.something().then((r) => { if (seq.isCurrent(n)) setData(r); });
 * };
 * ```
 *
 * 返回值是**跨渲染稳定**的对象（存在 ref 里）：这样把它放进 `useEffect` 依赖数组也
 * 不会每次渲染都重新执行——否则用它就得靠 eslint-disable 压住依赖告警。
 */
export function useSeq() {
  const seq = useRef(0);
  const api = useRef({
    next: () => ++seq.current,
    isCurrent: (n: number) => n === seq.current,
  });
  return api.current;
}
