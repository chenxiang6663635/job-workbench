/**
 * 行内输入（失焦提交）的提交与**失败回滚**。
 *
 * 为什么需要它：表格里的行内输入通常是 uncontrolled 的（挂载时取一次值），写入失败
 * （422 / 409 / 网络）时它们仍然显示用户刚敲的值，而列表重拉也回写不了它们——用户
 * 看到的是"已改"的假象，刷新后内容又"消失"（2026-09-23 二轮审计）。
 *
 * 约定：`patch` 返回 `false` 表示失败（其它返回值一律当成功），这是调用方与
 * 表格容器之间最小的一条契约——比让行内输入变成受控组件改动面小得多。
 */
export function commitInline(
  el: HTMLInputElement,
  current: string,
  patch: (value: string) => unknown,
): void {
  const next = el.value;
  if (next === current) return;
  Promise.resolve(patch(next)).then((ok) => {
    if (ok === false) el.value = current;
  });
}
