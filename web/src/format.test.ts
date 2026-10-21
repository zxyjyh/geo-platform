import { describe, expect, it } from "vitest";
import { formatRatio, pct } from "./format";

describe("formatRatio", () => {
  it("显示分子/分母和取整的百分比", () => {
    expect(formatRatio({ num: 8, den: 10 })).toBe("8/10（80%）");
    expect(formatRatio({ num: 2, den: 3 })).toBe("2/3（67%）");
  });
  it("分母为 0 显示无数据，不显示 0%", () => {
    expect(formatRatio({ num: 0, den: 0 })).toBe("无数据");
  });
});

describe("pct", () => {
  it("分母为 0 时给 null，趋势图据此断线", () => {
    expect(pct({ num: 1, den: 4 })).toBe(25);
    expect(pct({ num: 0, den: 0 })).toBeNull();
  });
});

import { selfcheckReason } from "./format";

describe("selfcheckReason", () => {
  it("first_aomi 只挡澳觅的三家中首位率", () => {
    expect(selfcheckReason(["first_aomi"], "first", "aomi")).toContain("首位");
    expect(selfcheckReason(["first_aomi"], "first", "mfood")).toBeNull();
    expect(selfcheckReason(["first_aomi"], "mention", "aomi")).toBeNull();
  });
  it("整天无效的失败挡住全部指标", () => {
    for (const f of ["coding_missing", "duplicate_qid", "n_valid"]) {
      expect(selfcheckReason([f], "share", "shanfeng")).not.toBeNull();
    }
  });
  it("没有失败返回 null", () => {
    expect(selfcheckReason([], "mention", "aomi")).toBeNull();
  });
});
