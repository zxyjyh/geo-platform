# InsGEO 功能借鉴实现

## 目标
分析 InsGEO 竞品平台，选取高价值功能实现到我们的项目。

## 已完成
- [x] 1a-1c 品牌监测基础功能
- [x] 1d 事实一致性检测（factcheck）
- [x] 增长指数（growth index）— 线性回归斜率，展示在看板
- [x] 竞品横向占位表（positioning matrix）— /positioning 页面

## 技术决策
- 增长指数：取最近 7 天 trend 数据，对 mention/first/share 的 aomi 比例做 np.polyfit(1) 线性回归，斜率就是增长指数
- 占位表：直接查 codings 表的 order_aomi/order_mfood/order_shanfeng，按 qid 聚合成矩阵
- 图标：TrendChartOutlined 不存在，换成 RiseOutlined

## 改动文件
- `app/analysis.py` — 新增 growth_index()
- `app/api/routes_dashboard.py` — dashboard 返回 growth 字段 + 新增 /positioning 路由
- `web/src/pages/Dashboard.tsx` — GrowthCard 组件
- `web/src/pages/Positioning.tsx` — 新页面
- `web/src/App.tsx` — 注册路由和菜单
- `web/src/types.ts` — PositioningData + growth 类型

## 当前分支
`feat/insgeo-enhancements` — 已提交 1 个 commit

## 待办
1. **T8 事实抽取真实数据**：LLM API 对长文本（~1000 字+）抽取 prompt 超时 300s，需要换更快模型（如 doubao-lite）或拆分长文本
2. **RDS 迁移**：用户需在 RDS 执行 `alembic upgrade head`
3. **InsGEO 密码**：用户在聊天中暴露了密码，建议修改
4. **后续可借鉴**：热门引用文章 Top 榜、首位推荐率/首屏提及率指标、AI 洞察分析师

## 验证
- 221 测试通过
- tsc --noEmit 无错误
- vite build 成功
- growth_index([1,2,3,4,5]) = 1.0
