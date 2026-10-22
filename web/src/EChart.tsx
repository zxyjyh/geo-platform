import { useEffect, useRef } from "react";
import * as echarts from "echarts";

/** 最小的 ECharts 包装：option 变了就重画，容器大小变了就 resize。 */
export default function EChart({ option, height = 300 }: { option: echarts.EChartsOption; height?: number | string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    chart.current = echarts.init(ref.current!);
    const ro = new ResizeObserver(() => chart.current?.resize());
    ro.observe(ref.current!);
    return () => {
      ro.disconnect();
      chart.current?.dispose();
    };
  }, []);
  useEffect(() => {
    chart.current?.setOption(option, true);
  }, [option]);
  return <div ref={ref} style={{ width: "100%", height }} />;
}
