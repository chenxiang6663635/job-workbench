// 成功播报的排队器（发送端见 lib/announce.ts，接收端见 components/LiveRegion.tsx）。
//
// 为什么需要它：读屏的 aria-live 区只在**文本真的变化**时才播报，而
//   - 同一帧里连发两条时，两次状态更新会被合并，前一条永远没被渲染（吞句）；
//   - 用 requestAnimationFrame 做「清空 → 落文本」在**后台标签页不触发**（rAF 被暂停），
//     任务在后台完成时那句话就永远播不出去。
// 这里改用 setTimeout（后台会被节流，但仍会触发）+ 队列：逐条播、条与条之间留一个
// 小间隔，让每次文本变化都能被读屏看见。
//
// 纯逻辑、不碰 DOM：LiveRegion 负责把 emit 接到 state 上，单测直接驱动 scheduler。
export const ANNOUNCE_GAP_MS = 150;

export type AnnounceScheduler = {
  setTimeout: (fn: () => void, ms: number) => number;
  clearTimeout: (handle: number) => void;
};

export type AnnounceQueue = {
  push: (raw: string) => void;
  dispose: () => void;
};

const defaultScheduler: AnnounceScheduler = {
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (handle) => window.clearTimeout(handle),
};

export function createAnnounceQueue(
  emit: (text: string) => void,
  scheduler: AnnounceScheduler = defaultScheduler
): AnnounceQueue {
  const pending: string[] = [];
  let timer: number | null = null;
  let disposed = false;

  const step = () => {
    timer = null;
    if (disposed) return;
    const next = pending.shift();
    if (next === undefined) return;
    // 清空与落文本分属两个宏任务：同句重播也要被读屏看见（光靠重渲不播）
    emit("");
    timer = scheduler.setTimeout(() => {
      timer = null;
      if (disposed) return;
      emit(next);
      if (pending.length) timer = scheduler.setTimeout(step, ANNOUNCE_GAP_MS);
    }, 0);
  };

  return {
    push(raw) {
      const text = raw.trim();
      if (!text || disposed) return;
      pending.push(text);
      // 已有计时器在飞就只入队：连发不会各排各的，顺序即入队顺序
      if (timer === null) timer = scheduler.setTimeout(step, 0);
    },
    dispose() {
      disposed = true;
      pending.length = 0;
      if (timer !== null) {
        scheduler.clearTimeout(timer);
        timer = null;
      }
    },
  };
}
