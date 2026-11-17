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

import { highlightSegments, platformLabel, weakReasons } from "./format";

describe("platformLabel", () => {
  it("显示平台名称和引用次数", () => {
    expect(platformLabel({ key: "zhihu", name: "知乎", count: 0, verified: false })).toBe("知乎 0");
    expect(platformLabel({ key: "sohu", name: "搜狐", count: 22, verified: true })).toBe("搜狐 22");
  });
});

describe("weakReasons", () => {
  it("把原因翻成带分子分母的话", () => {
    const w = { qid: "Q01", text: "", n_runs: 7, aomi_mentions: 3, aomi_first: 2, competitor_first: 4,
      reasons: ["mention_low", "competitor_ahead"] };
    expect(weakReasons(w)).toEqual(["提及不足：3/7", "被竞品压住：mFood 或闪蜂排第一 4 次 vs 澳觅 2 次"]);
  });
});

describe("highlightSegments", () => {
  it("按别名切分，命中的段标出属于哪家", () => {
    const segs = highlightSegments("推荐澳觅和mFood，閃蜂也行", { aomi: ["澳觅"], mfood: ["mFood"], shanfeng: ["閃蜂"] });
    expect(segs).toEqual([
      { text: "推荐", entity: null }, { text: "澳觅", entity: "aomi" }, { text: "和", entity: null },
      { text: "mFood", entity: "mfood" }, { text: "，", entity: null }, { text: "閃蜂", entity: "shanfeng" },
      { text: "也行", entity: null },
    ]);
  });
  it("长别名优先，正则特殊字符不出错", () => {
    const segs = highlightSegments("澳門Food(a+)", { aomi: [], mfood: ["澳門Food", "Food"], shanfeng: ["(a+)"] });
    expect(segs.map((s) => s.entity)).toEqual(["mfood", "shanfeng"]);
  });
});

import { missingNotice, trendValue } from "./format";

const day = (over: Partial<import("./types").DailyMetrics> = {}) => ({
  date: "2026-10-21", channel: "api-custom", n_expected: 10, n_valid: 6, n_reps: 1,
  missing_qids: ["Q05", "Q09", "Q10", "Q11"],
  mention: { aomi: { num: 5, den: 6 }, mfood: { num: 4, den: 6 }, shanfeng: { num: 0, den: 6 } },
  first: { aomi: { num: 3, den: 6 }, mfood: { num: 1, den: 6 }, shanfeng: { num: 0, den: 6 } },
  share: { aomi: { num: 5, den: 9 }, mfood: { num: 4, den: 9 }, shanfeng: { num: 0, den: 9 } },
  selfcheck_failures: [], ...over,
});

describe("trendValue", () => {
  it("自检未通过的点不画（null），和表格一样不出数", () => {
    expect(trendValue(day(), "mention", "aomi")).toBeCloseTo(83.33, 1);
    expect(trendValue(day({ selfcheck_failures: ["coding_missing"] }), "mention", "aomi")).toBeNull();
    expect(trendValue(day({ selfcheck_failures: ["first_aomi"] }), "first", "aomi")).toBeNull();
    expect(trendValue(day({ selfcheck_failures: ["first_aomi"] }), "mention", "aomi")).not.toBeNull();
  });
});

describe("missingNotice", () => {
  it("部分缺题写 x/有效题 并列出缺的题（Review Focus 2）", () => {
    expect(missingNotice(day(), "今天")).toBe("今天只采到 6/10 题，缺：Q05、Q09、Q10、Q11");
  });
  it("全缺和不缺", () => {
    expect(missingNotice(day({ n_valid: 0 }), "10-20")).toBe("10-20没有有效数据（应采 10 题）");
    expect(missingNotice(day({ missing_qids: [], n_valid: 10 }), "今天")).toBeNull();
  });
});

import { cstToday } from "./format";

describe("cstToday", () => {
  it("按北京时间算今天，与浏览器时区无关", () => {
    expect(cstToday(new Date("2026-10-21T22:00:00Z"))).toBe("2026-10-22");
    expect(cstToday(new Date("2026-10-21T15:59:59Z"))).toBe("2026-10-21");
  });
});

import { plainSnippet } from "./format";

describe("plainSnippet", () => {
  it("去掉 Markdown 记号，只留文字", () => {
    expect(plainSnippet("### 2. **澳覓 App｜適合外賣+商超即配**")).toBe("2. 澳覓 App｜適合外賣+商超即配");
    expect(plainSnippet("| **澳觅** | 多数订单约 30–60 分钟 | 一站式 |")).toBe("澳觅 · 多数订单约 30–60 分钟 · 一站式");
    expect(plainSnippet("- 公开资料显示 `澳觅`")).toBe("公开资料显示 澳觅");
  });
});

import { prevText } from "./format";

describe("prevText", () => {
  it("前一天也要过自检：未通过不出数", () => {
    expect(prevText(undefined, "mention", "aomi")).toBe("无数据");
    expect(prevText(day(), "mention", "aomi")).toBe("5/6（83%）");
    expect(prevText(day({ selfcheck_failures: ["coding_missing"] }), "mention", "aomi")).toBe("自检未通过");
    expect(prevText(day({ selfcheck_failures: ["first_aomi"] }), "first", "aomi")).toBe("自检未通过");
    expect(prevText(day({ selfcheck_failures: ["first_aomi"] }), "mention", "aomi")).toBe("5/6（83%）");
  });
});

import { coveredQs, repsChanges } from "./format";

describe("repsChanges", () => {
  it("只在有数据的相邻两天 n_reps 不同时返回，空数据日跳过", () => {
    const t = [day({ date: "2026-10-20", n_reps: 1 }), day({ date: "2026-10-21", n_reps: 0 }),
               day({ date: "2026-10-22", n_reps: 2 }), day({ date: "2026-10-23", n_reps: 2 })];
    expect(repsChanges(t)).toEqual([{ date: "2026-10-22", reps: 2 }]);
  });
  it("第一天不算变化", () => expect(repsChanges([day({ n_reps: 2 })])).toEqual([]));
});

describe("每题多次时按题数提示", () => {
  it("n_valid 是回答数，缺题提示和覆盖题数按题算", () => {
    const m = day({ n_valid: 12, n_reps: 2 });     // 6 题各 2 次
    expect(coveredQs(m)).toBe(6);
    expect(missingNotice(m, "今天")).toBe("今天只采到 6/10 题，缺：Q05、Q09、Q10、Q11");
  });
});

import { lagLabel } from "./format";

describe("lagLabel", () => {
  const base = { lag_days: 5, left_censored: false, publish_suspect: false, publish_time: "2026-09-01T09:00:00+08:00" };
  it("左删失优先，不出天数", () => expect(lagLabel({ ...base, lag_days: null, left_censored: true })).toEqual({ tag: "监测开始前可能已被引用" }));
  it("发布时间晚于首次被引", () => expect(lagLabel({ ...base, lag_days: null, publish_suspect: true })).toEqual({ tag: "发布时间晚于首次被引" }));
  it("没有发布时间显示 —", () => expect(lagLabel({ ...base, lag_days: null, publish_time: null })).toEqual({ text: "—" }));
  it("正常给天数", () => expect(lagLabel(base)).toEqual({ text: "5 天" }));
});
