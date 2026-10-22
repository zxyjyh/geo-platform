// 字段名与后端 Task 9 的 JSON 一一对应
export type Entity = "aomi" | "mfood" | "shanfeng";
export const ENTITIES: Entity[] = ["aomi", "mfood", "shanfeng"];
export const ENTITY_NAME: Record<Entity, string> = { aomi: "澳觅", mfood: "mFood", shanfeng: "闪蜂" };

export interface Ratio {
  num: number;
  den: number;
}

export interface DailyMetrics {
  date: string;
  channel: string;
  n_expected: number;
  n_valid: number;   // 有效回答数，每题问多次时大于题数
  n_reps: number;    // 当天每题最多问了几次，没有有效数据时为 0
  missing_qids: string[];
  mention: Record<Entity, Ratio>;
  first: Record<Entity, Ratio>;
  share: Record<Entity, Ratio>;
  selfcheck_failures: string[];
}

export interface DashboardData {
  date: string;
  channel: string;
  latest_date: string | null;
  first_date: string | null;
  today: string; // 北京时间的今天，由后端给出
  metrics: DailyMetrics;
  by_scene: { scene: string; qids: string[]; metrics: DailyMetrics }[];
  job: { status: string; n_ok: number; n_failed: number; message: string } | null;
  usage: { billed_searches: number; input_tokens: number; output_tokens: number; est_cost_yuan: number | null };
}

export interface AttributionHit {
  run_id: string;
  qid: string;
  marks: string[];
  owned_source: boolean;
}

/** 品牌归因：分母是全部题（含带品牌名的）中提到澳觅的回答。configured=false 时不出数。 */
export interface AttributionDay {
  date: string;
  channel: string;
  version: number;
  configured: boolean;
  text: Ratio;
  source: Ratio;
  hits: AttributionHit[];
}

export interface BrandMark {
  kind: string;
  value: string;
}

export const MARK_KIND_LABEL: Record<string, string> = {
  website: "官网", phone: "客服电话", app_store: "应用商店名", mini_program: "小程序名", official_account: "公众号名", other: "其他",
};

/** 一篇文章在所选时间段内的引用周期（spec §4.6.1）。 */
export interface CitationLife {
  url_norm: string;
  url: string;
  title: string;
  domain: string;
  platform_key: string | null;
  n_citations: number;
  first_date: string;
  last_date: string;
  active_days: number;
  span_days: number;
  persistence: number;
  energy: number;
  publish_time: string | null;
  lag_days: number | null;
  left_censored: boolean;
  publish_suspect: boolean;
  external_geo: boolean;
  is_owned: boolean;
}

export interface PlatformCount {
  key: string;
  name: string;
  count: number;
  verified: boolean;
}

export interface WeakQuestion {
  qid: string;
  text: string;
  n_runs: number;
  aomi_mentions: number;
  aomi_first: number;
  competitor_first: number;
  reasons: string[];
}

export interface RefArticle {
  url_norm: string;
  url: string;
  title: string;
  domain: string;
  platform_key: string | null;
  count: number;
  external_geo: boolean;
}

export interface RunItem {
  run_id: string;
  collect_date: string;
  qid: string;
  question: string | null;
  scene: string | null;
  aomi_snippet: string | null;
  round: string;
  channel: string;
  status: string;
  mention: Record<Entity, boolean> | null;
  order: Record<Entity, number | null> | null;
  sources_count: number;
}

export function orderText(order: Record<Entity, number | null> | null): string {
  if (!order) return "—";
  const ranked = ENTITIES.filter((e) => order[e] !== null).sort((a, b) => order[a]! - order[b]!);
  return ranked.length ? ranked.map((e) => ENTITY_NAME[e]).join(" > ") : "三家都没提";
}
