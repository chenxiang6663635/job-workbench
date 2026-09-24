import { describe, expect, it } from "vitest";

import { isGateOpen, isMismatch, requiresTyping } from "../../src/lib/dangerGate";

describe("requiresTyping", () => {
  it("只有 confirm 档不需要手打内容", () => {
    expect(requiresTyping("confirm")).toBe(false);
    expect(requiresTyping("phrase")).toBe(true);
    expect(requiresTyping("name")).toBe(true);
  });
});

describe("isGateOpen", () => {
  it("confirm 档直接放行", () => {
    expect(isGateOpen("confirm", undefined, "")).toBe(true);
  });

  it("phrase 档要求逐字符相等（大小写有意义）", () => {
    expect(isGateOpen("phrase", "DELETE", "DELETE")).toBe(true);
    expect(isGateOpen("phrase", "DELETE", "delete")).toBe(false);
    expect(isGateOpen("phrase", "DELETE", "DELETE!")).toBe(false);
    expect(isGateOpen("phrase", "DELETE", "")).toBe(false);
  });

  it("首尾空白被容忍，中间不放过", () => {
    expect(isGateOpen("phrase", "DELETE", "  DELETE  ")).toBe(true);
    expect(isGateOpen("phrase", "DELETE", "DE LETE")).toBe(false);
  });

  it("name 档同样要求逐字符相等", () => {
    expect(isGateOpen("name", "demo", "demo")).toBe(true);
    expect(isGateOpen("name", "demo", "demo2")).toBe(false);
  });

  it("challenge 缺失时一律不放行（门禁坏掉宁可拦住）", () => {
    expect(isGateOpen("phrase", undefined, "DELETE")).toBe(false);
    expect(isGateOpen("name", "", "anything")).toBe(false);
  });
});

describe("isMismatch", () => {
  it("还没输入时不报错（一打开就红字是坏体验）", () => {
    expect(isMismatch("phrase", "DELETE", "")).toBe(false);
    expect(isMismatch("phrase", "DELETE", "   ")).toBe(false);
  });

  it("输入了但不对才提示", () => {
    expect(isMismatch("phrase", "DELETE", "DEL")).toBe(true);
    expect(isMismatch("phrase", "DELETE", "DELETE")).toBe(false);
  });

  it("confirm 档永远不会处于不匹配状态", () => {
    expect(isMismatch("confirm", undefined, "随便打的")).toBe(false);
  });
});
