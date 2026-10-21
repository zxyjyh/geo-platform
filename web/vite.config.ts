/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // 本地开发：/api 代理到 uvicorn（uv run uvicorn app.api:create_app --factory）
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    rollupOptions: {
      // antd、echarts 各自单独打包：业务代码改动不会让浏览器重新下载这两个大库
      output: { manualChunks: { antd: ["antd", "@ant-design/icons"], echarts: ["echarts"], react: ["react", "react-dom", "react-router-dom"] } },
    },
    // 内部后台，antd / echarts 单包本身就超过 500kB，按实际大小设阈值
    chunkSizeWarningLimit: 1200,
  },
  test: { include: ["src/**/*.test.ts"] },
});
