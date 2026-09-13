// 临时文件：验证 no-use-before-define 规则能否抓住 TDZ（跑完即删）
export function Check() {
  const x = b;
  const b = 1;
  return x + b;
}
