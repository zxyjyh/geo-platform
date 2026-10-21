import type { Entity, Ratio } from "./types";

export type Metric = "mention" | "first" | "share";

/** 比率一律显示成"分子/分母（百分比）"；分母为 0 显示"无数据"，不显示 0%。 */
export function formatRatio(r: Ratio): string {
  if (r.den === 0) return "无数据";
  return `${r.num}/${r.den}（${Math.round((r.num * 100) / r.den)}%）`;
}

/** 趋势图用：分母为 0 返回 null，折线在这一天断开。 */
export function pct(r: Ratio): number | null {
  return r.den === 0 ? null : (r.num * 100) / r.den;
}

// 后端 app/metrics.py 的自检名：这几条说明当天数据整体不可信，所有指标都不出数
const WHOLE_DAY: Record<string, string> = {
  coding_missing: "部分回答缺少当前别名表版本的编码（重算未完成）",
  duplicate_qid: "同一题当天有多条有效回答",
  n_valid: "有效回答数超过题数",
};

/** 这个指标该不该出数：返回不出数的原因，没有问题返回 null。 */
export function selfcheckReason(failures: string[], metric: Metric, entity: Entity): string | null {
  for (const f of failures) {
    if (WHOLE_DAY[f]) return WHOLE_DAY[f];
  }
  if (metric === "first" && failures.includes(`first_${entity}`)) return "三家中首位数大于提及数";
  return null;
}
