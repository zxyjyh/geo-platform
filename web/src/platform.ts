import { createContext, useContext } from "react";

/** 被测的大模型（runs.platform）。顶栏全局选择，概览 / 信源 / 回答记录 / 优化建议共用。 */
export type ModelPlatform = "doubao" | "qianwen";

// 千问采集还没接入：先占位不可选，免得选了千问却看到豆包的数。接入后去掉 disabled，后端 ModelPlatform 同步加上
export const PLATFORMS: { value: ModelPlatform; label: string; disabled?: boolean }[] = [
  { value: "doubao", label: "豆包" },
  { value: "qianwen", label: "千问（待接入）", disabled: true },
];

export const PlatformContext = createContext<ModelPlatform>("doubao");
export const usePlatform = () => useContext(PlatformContext);
