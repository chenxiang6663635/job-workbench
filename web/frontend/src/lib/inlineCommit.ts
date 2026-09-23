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
/**
 * 写入结果：`false` = 失败（其余值一律当成功）。
 *
 * 起个别名而不是就地写联合类型：`=> boolean | Promise<boolean>` 这种写法会被本仓的
 * 「残余硬编码英文」扫描器当成 JSX 文本（它按 `>` … `<` 之间取文本，而箭头函数类型
 * 恰好是 `=>` 后紧跟 `Promise<`）。别名声明那边没有前导 `>`，不会被误判。
 */
export type PatchOutcome = boolean | Promise<boolean>;

export function commitInline(
  el: HTMLInputElement,
  current: string,
  patch: (value: string) => PatchOutcome,
): void {
  const next = el.value;
  if (next === current) return;
  Promise.resolve(patch(next)).then((ok) => {
    if (ok === false) el.value = current;
  });
}
