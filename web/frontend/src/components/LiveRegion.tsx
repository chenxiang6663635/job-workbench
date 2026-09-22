import { useEffect, useState } from "react";
import { ANNOUNCE_EVENT } from "../lib/announce";
import { createAnnounceQueue } from "../lib/announceQueue";

// UX-6（体检）：全站唯一的 aria-live 播报区（发送端见 lib/announce.ts）。
//
// 为什么要有它：批处理型的成功反馈（保存 / 导入 / 抓取成功）此前只体现在界面
// 重新渲染或一行小字上——视觉用户看得到，读屏用户得到的是一片沉默。
// `ErrorBanner` 覆盖了失败侧（`role="alert"`，会被打断播出），成功侧缺一个
// 不着痕迹的落点，这里补上：**一个_app 只有一个消费者**，多了就会重复播报。
//
// 排队与计时都交给 lib/announceQueue（2026-09-22 审查 MINOR）：
// 同帧连发不吞句；后台标签页也能播（rAF 会被暂停，setTimeout 仍会触发）。
export default function LiveRegion() {
  const [notice, setNotice] = useState<{ text: string; seq: number }>({
    text: "",
    seq: 0,
  });

  useEffect(() => {
    const queue = createAnnounceQueue((text) =>
      setNotice((prev) => ({ text, seq: prev.seq + 1 }))
    );
    const onAnnounce = (event: Event) => {
      queue.push(String((event as CustomEvent).detail ?? ""));
    };
    window.addEventListener(ANNOUNCE_EVENT, onAnnounce);
    return () => {
      window.removeEventListener(ANNOUNCE_EVENT, onAnnounce);
      queue.dispose();
    };
  }, []);

  return (
    <div role="status" aria-live="polite" className="sr-only">
      {notice.text}
    </div>
  );
}
