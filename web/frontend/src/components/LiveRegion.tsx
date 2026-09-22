import { useEffect, useState } from "react";
import { ANNOUNCE_EVENT } from "../lib/announce";

// UX-6（体检）：全站唯一的 aria-live 播报区（发送端见 lib/announce.ts）。
//
// 为什么要有它：批处理型的成功反馈（保存 / 导入 / 抓取成功）此前只体现在界面
// 重新渲染或一行小字上——视觉用户看得到，读屏用户得到的是一片沉默。
// `ErrorBanner` 覆盖了失败侧（`role="alert"`，会被打断播出），成功侧缺一个
// 不着痕迹的落点，这里补上：**一个_app 只有一个消费者**，多了就会重复播报。
export default function LiveRegion() {
  const [notice, setNotice] = useState<{ text: string; seq: number }>({
    text: "",
    seq: 0,
  });

  useEffect(() => {
    const onAnnounce = (event: Event) => {
      const text = String((event as CustomEvent).detail ?? "").trim();
      if (!text) return;
      // 同句重复时，光靠重渲不会被读屏再念一次：先把文本清空、下一帧放回，
      // 强制让它看到一次真正的内容变化
      setNotice((prev) => ({ text: "", seq: prev.seq + 1 }));
      requestAnimationFrame(() => setNotice((prev) => ({ text, seq: prev.seq + 1 })));
    };
    window.addEventListener(ANNOUNCE_EVENT, onAnnounce);
    return () => window.removeEventListener(ANNOUNCE_EVENT, onAnnounce);
  }, []);

  return (
    <div role="status" aria-live="polite" className="sr-only">
      {notice.text}
    </div>
  );
}
