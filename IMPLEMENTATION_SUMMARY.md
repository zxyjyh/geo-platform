# 竞品横向占位表（Competitor Positioning Matrix）实现总结

## 完成时间
2026-10-23

## 实现内容

### 1. 后端 API
**文件**: `app/api/routes_dashboard.py`

新增接口 `GET /api/dashboard/positioning`

**参数**:
- `date` (可选): 日期，默认取最新一天
- `channel` (可选): 渠道
- `platform` (可选): 平台，默认 "doubao"

**返回格式**:
```json
{
  "date": "2026-10-23",
  "channel": "api-custom",
  "questions": [
    {"qid": "Q01", "text": "澳门外卖平台推荐", "scene": "外卖"}
  ],
  "brands": ["aomi", "mfood", "shanfeng"],
  "matrix": {
    "Q01": {"aomi": 1, "mfood": 2, "shanfeng": null}
  }
}
```

**查询逻辑**:
- 从 `questions` 表获取指定版本的所有题目
- 从 `codings` 表 join `runs` 表获取每道题的品牌排位
- 返回 `order_aomi`, `order_mfood`, `order_shanfeng` 字段
- `null` 表示该题未提及该品牌

### 2. 前端类型定义
**文件**: `web/src/types.ts`

新增接口:
```typescript
export interface PositioningData {
  date: string;
  channel: string;
  questions: { qid: string; text: string; scene: string }[];
  brands: string[];
  matrix: Record<string, Record<string, number | null>>;
}
```

### 3. 前端页面
**文件**: `web/src/pages/Positioning.tsx`

**功能**:
- 矩阵表格展示：行=题目，列=品牌，格子=名次
- 日期选择器（顶部）
- 颜色区分：
  - 名次 1：绿色背景 (#d4edda)
  - 名次 2-3：浅蓝背景 (#d1ecf1)
  - 名次 4+：灰色背景 (#e9ecef)
  - 未提及：显示 "—"
- 题目显示：qid + 文本前 20 字
- 品牌列头带颜色标识（澳觅紫、mFood橙、闪蜂绿）
- 响应式表格，支持横向滚动

### 4. 路由和菜单注册
**文件**: `web/src/App.tsx`

**修改**:
- 导入 `TableOutlined` 图标
- 导入 `Positioning` 组件
- PAGES 数组新增：`{ key: "/positioning", icon: <TableOutlined />, label: "竞品占位", group: "数据" }`
- 位置：在"信源分析"下面
- Routes 新增：`<Route path="/positioning" element={<Positioning />} />`

## 验证结果

✅ TypeScript 类型检查通过：`cd web && npx tsc --noEmit` 无错误  
✅ Python 语法检查通过：`python3 -m py_compile app/api/routes_dashboard.py`  
✅ 未修改现有 API  
✅ 前端使用 antd Table 组件  
✅ 颜色区分符合需求

## 使用方式

1. 启动后端服务
2. 访问前端 `/positioning` 路径
3. 选择日期查看当天的竞品占位矩阵
4. 表格显示每道题中三个品牌的排位情况

## 技术要点

- 后端使用 SQLAlchemy 的 `select().join()` 查询
- 前端使用 antd 的 Table 和 DatePicker 组件
- 名次用内联样式渲染，避免额外 CSS 文件
- 支持多 run 情况下取第一条数据（可后续优化为聚合）
