import type { DailyMetrics, Entity, PlatformCount, Ratio, WeakQuestion } from "./types";

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

/** 平台推荐：0 次的平台照样列出，标"未验证"。 */
export function platformLabel(p: PlatformCount): string {
  return p.count === 0 ? `${p.name} 0（未验证）` : `${p.name} ${p.count}`;
}

/** 短板原因翻成带分子分母的话。后端只给"mFood 或闪蜂排第一"的合计，不分家。 */
export function weakReasons(w: WeakQuestion): string[] {
  const out: string[] = [];
  if (w.reasons.includes("mention_low")) out.push(`提及不足：${w.aomi_mentions}/${w.n_runs}`);
  if (w.reasons.includes("competitor_ahead")) {
    out.push(`被竞品压住：mFood 或闪蜂排第一 ${w.competitor_first} 次 vs 澳觅 ${w.aomi_first} 次`);
  }
  return out;
}

export interface Segment {
  text: string;
  entity: Entity | null;
}

/** 把回答原文按别名切段，用来高亮三家的名字。长别名优先匹配（澳門Food 不会被 Food 截断）。 */
export function highlightSegments(text: string, aliases: Record<Entity, string[]>): Segment[] {
  const owner = new Map<string, Entity>();
  (Object.keys(aliases) as Entity[]).forEach((e) => aliases[e].forEach((a) => a && owner.set(a, e)));
  const names = [...owner.keys()].sort((a, b) => b.length - a.length);
  if (names.length === 0) return text ? [{ text, entity: null }] : [];
  const re = new RegExp(names.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  const out: Segment[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push({ text: text.slice(last, m.index), entity: null });
    out.push({ text: m[0], entity: owner.get(m[0])! });
    last = m.index! + m[0].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), entity: null });
  return out;
}

/** 趋势图上一个点的值：自检未通过或分母为 0 时为 null（折线断开），和表格"不出数"保持一致。 */
export function trendValue(d: DailyMetrics, metric: Metric, entity: Entity): number | null {
  return selfcheckReason(d.selfcheck_failures, metric, entity) ? null : pct(d[metric][entity]);
}

/** 缺题提示：分母写实际有效题数并列出缺的题；不缺返回 null。 */
export function missingNotice(m: DailyMetrics, dayWord: string): string | null {
  if (m.missing_qids.length === 0) return null;
  if (m.n_valid === 0) return `${dayWord}没有有效数据（应采 ${m.n_expected} 题）`;
  return `${dayWord}只采到 ${m.n_valid}/${m.n_expected} 题，缺：${m.missing_qids.join("、")}`;
}

/** 北京时间的今天（YYYY-MM-DD）。补跑只允许当天，日期必须按 Asia/Shanghai 算。 */
export function cstToday(at: Date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(at);
}

/** 提及摘要是回答原文（Markdown）里截出来的一句：列表里展示时去掉记号，文字不改。 */
export function plainSnippet(s: string): string {
  return s
    .replace(/^\s*(#{1,6}\s+|[-*+]\s+|>\s+)/, "")
    .replace(/\*\*|__|`/g, "")
    .replace(/^\s*\|\s*|\s*\|\s*$/g, "")
    .replace(/\s*\|\s*/g, " · ")
    .trim();
}

/** KPI 卡和竞品对比里的"前一天 x/y"：和当天一样要过自检，未通过不出数。 */
export function prevText(prev: DailyMetrics | undefined, metric: Metric, entity: Entity): string {
  if (!prev) return "无数据";
  return selfcheckReason(prev.selfcheck_failures, metric, entity) ? "自检未通过" : formatRatio(prev[metric][entity]);
}
