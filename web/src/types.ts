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
  n_valid: number;
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
  metrics: DailyMetrics;
  job: { status: string; n_ok: number; n_failed: number; message: string } | null;
  usage: { billed_searches: number; input_tokens: number; output_tokens: number; est_cost_yuan: number | null };
}

export interface PlatformCount {
  key: string;
  name: string;
  count: number;
  verified: boolean;
}
