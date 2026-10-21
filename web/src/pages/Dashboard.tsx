import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Card, Col, DatePicker, Descriptions, Row, Segmented, Select, Space, Switch, Table, Tag, Tooltip, Typography } from "antd";
import { AimOutlined, PercentageOutlined, QuestionCircleOutlined, TrophyOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { get } from "../api";
import EChart from "../EChart";
import { formatRatio, missingNotice, pct, plainSnippet, selfcheckReason, trendValue, type Metric } from "../format";
import { ENTITIES, ENTITY_NAME, orderText, type DailyMetrics, type DashboardData, type Entity, type RunItem } from "../types";

const METRICS: Record<Metric, { label: string; hint: string; icon: JSX.Element }> = {
  mention: { label: "提及率", icon: <AimOutlined />, hint: "提到该平台的回答数 / 当天有效回答数（只算不带品牌名的题）" },
  first: { label: "三家中首位率", icon: <TrophyOutlined />,
    hint: "只在澳觅、mFood、闪蜂三家之间比先后：排第一的回答数 / 有效回答数。Klook 等其他平台不参与排序" },
  share: { label: "提及份额", icon: <PercentageOutlined />, hint: "该平台被提及次数 / 三家被提及次数之和" },
};
const COLORS: Record<Entity, string> = { aomi: "#5B5CF6", mfood: "#E8590C", shanfeng: "#12B886" };
const JOB_TAG: Record<string, { color: string; text: string }> = {
  done: { color: "green", text: "完成" }, failed: { color: "red", text: "失败" },
  running: { color: "blue", text: "运行中" }, requested: { color: "gold", text: "排队中" },
};

function cell(m: DailyMetrics | undefined, metric: Metric, e: Entity) {
  if (!m) return <Typography.Text type="secondary">无数据</Typography.Text>;
  const reason = selfcheckReason(m.selfcheck_failures, metric, e);
  return reason ? <Typography.Text type="danger">自检未通过：{reason}</Typography.Text>
    : <span className="num">{formatRatio(m[metric][e])}</span>;
}

export default function Dashboard() {
  const nav = useNavigate();
  const [query, setQuery] = useState<{ date?: string; channel?: string }>({});
  const [data, setData] = useState<DashboardData | null>(null);
  const [trend, setTrend] = useState<DailyMetrics[]>([]);
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("mention");
  const [showCompetitors, setShowCompetitors] = useState(true);

  useEffect(() => {
    let stale = false; // 快速切换日期时，旧请求晚到不能覆盖新数据
    setError(null);
    get<DashboardData>("/dashboard", query)
      .then((d) => {
        if (stale) return;
        setData(d);
        const end = dayjs(d.date);
        get<DailyMetrics[]>("/dashboard/trend", { start: end.subtract(29, "day").format("YYYY-MM-DD"), end: d.date, channel: d.channel })
          .then((t) => !stale && setTrend(t))
          .catch((e) => !stale && setError(`趋势加载失败：${e.message}`));
        get<{ items: RunItem[] }>("/runs", { date_from: d.date, date_to: d.date, round: "daily", channel: d.channel, size: 100 })
          .then((r) => !stale && setRuns([...r.items].sort((a, b) => a.qid.localeCompare(b.qid))))
          .catch((e) => !stale && setError(`逐题结果加载失败：${e.message}`));
      })
      .catch((e) => !stale && setError(String(e.message || e)));
    return () => { stale = true; };
  }, [query]);

  const prev = useMemo(() => {
    if (!data) return undefined;
    const want = dayjs(data.date).subtract(1, "day").format("YYYY-MM-DD");
    return trend.find((t) => t.date === want);
  }, [data, trend]);

  const trendOption = useMemo(() => ({
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: unknown) => {
        const ps = params as { axisValue: string; dataIndex: number }[];
        const d = trend[ps[0].dataIndex];
        const lines = ENTITIES.map((e) => {
          const r = selfcheckReason(d.selfcheck_failures, metric, e);
          return `${ENTITY_NAME[e]}：${r ? `自检未通过（${r}）` : formatRatio(d[metric][e])}`;
        });
        return [`${d.date}${d.n_valid === 0 ? "（缺数据）" : ""}`, ...lines].join("<br/>");
      },
    },
    legend: { data: ENTITIES.map((e) => ENTITY_NAME[e]), left: 0 },
    grid: { left: 44, right: 16, top: 40, bottom: 28 },
    xAxis: { type: "category" as const, data: trend.map((t) => t.date.slice(5)) },
    yAxis: { type: "value" as const, min: 0, max: 100, axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { type: "dashed" as const } } },
    // 缺数据或自检未通过的日期值为 null，折线断开；孤立点强制画出
    series: ENTITIES.filter((e) => e === "aomi" || showCompetitors).map((e) => ({
      name: ENTITY_NAME[e], type: "line" as const, smooth: true, connectNulls: false, showAllSymbol: true, symbolSize: 6,
      itemStyle: { color: COLORS[e] }, lineStyle: { width: e === "aomi" ? 2.5 : 1.5, type: e === "aomi" ? "solid" as const : "dashed" as const },
      data: trend.map((t) => trendValue(t, metric, e)),
    })),
  }), [trend, metric, showCompetitors]);

  if (!data) return error ? <Alert type="error" showIcon message={error} /> : null;
  const m = data.metrics;
  const isToday = data.date === data.today;
  const dayWord = isToday ? "今天" : data.date;
  const notice = missingNotice(m, dayWord);
  const tracked = data.first_date ? dayjs(data.date).diff(dayjs(data.first_date), "day") + 1 : 0;

  const barEntities = [...ENTITIES].sort((a, b) => (pct(m[metric][b]) ?? -1) - (pct(m[metric][a]) ?? -1));
  // 名次 = 1 + 严格高于澳觅的家数；有人和澳觅相同就是"并列"
  const aomiPct = pct(m[metric].aomi) ?? -1;
  const aomiRank = 1 + ENTITIES.filter((e) => (pct(m[metric][e]) ?? -1) > aomiPct).length;
  const aomiTied = ENTITIES.some((e) => e !== "aomi" && (pct(m[metric][e]) ?? -1) === aomiPct);
  const barBlocked = ENTITIES.some((e) => selfcheckReason(m.selfcheck_failures, metric, e));
  const barOption = {
    grid: { left: 56, right: 70, top: 10, bottom: 24 },
    xAxis: { type: "value" as const, min: 0, max: 100, axisLabel: { formatter: "{value}%" }, splitLine: { lineStyle: { type: "dashed" as const } } },
    yAxis: { type: "category" as const, inverse: true, data: barEntities.map((e) => ENTITY_NAME[e]) },
    series: [{
      type: "bar" as const, barWidth: 22,
      data: barEntities.map((e) => ({ value: pct(m[metric][e]), itemStyle: { color: e === "aomi" ? COLORS.aomi : "#D9DCE3", borderRadius: 4 } })),
      label: { show: true, position: "right" as const, formatter: (p: { dataIndex: number }) => formatRatio(m[metric][barEntities[p.dataIndex]]) },
    }],
  };

  const kpis = (Object.keys(METRICS) as Metric[]).map((k) => (
    <Col xs={24} sm={12} xl={6} key={k}>
      <Card className="ab-card" size="small">
        <Tooltip title={METRICS[k].hint}><div className="ab-kpi-title">{METRICS[k].icon}澳觅{METRICS[k].label}</div></Tooltip>
        <div className="ab-kpi-value">{cell(m, k, "aomi")}</div>
        <div className="ab-kpi-sub">前一天 {prev ? formatRatio(prev[k].aomi) : "无数据"}</div>
      </Card>
    </Col>
  ));

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row justify="space-between" align="middle" gutter={[16, 8]}>
        <Col>
          <Space align="baseline">
            <Typography.Title level={3} style={{ margin: 0 }}>澳觅</Typography.Title>
            <Typography.Text type="secondary">{tracked ? `已追踪 ${tracked} 天` : "尚无数据"}</Typography.Text>
          </Space>
          <div><Typography.Text type="secondary">
            一览澳觅在豆包回答里的提及、三家先后与趋势。数据来自 {data.channel}（方舟模型 + 字节搜索），不是豆包 App 的表现。
          </Typography.Text></div>
        </Col>
        <Col>
          <Space wrap>
            <Typography.Text type="secondary">筛选：</Typography.Text>
            <DatePicker allowClear={false} value={dayjs(data.date)}
              onChange={(d) => d && setQuery((q) => ({ ...q, date: d.format("YYYY-MM-DD") }))}
              disabledDate={(d) => d.format("YYYY-MM-DD") > data.today} />
            <Select value={data.channel} style={{ width: 130 }} onChange={(c) => setQuery({ channel: c })}
              options={[{ value: "api-custom" }, { value: "api-plugin" }]} />
            {data.latest_date && data.latest_date !== data.date && (
              <Typography.Link onClick={() => setQuery((q) => ({ ...q, date: data.latest_date! }))}>回到最近一天</Typography.Link>
            )}
          </Space>
        </Col>
      </Row>

      {error && <Alert type="error" showIcon closable message={error} onClose={() => setError(null)} />}
      {notice && <Alert type="warning" showIcon message={notice} />}

      <Row gutter={[16, 16]}>
        {kpis.slice(0, 3)}
        <Col xs={24} sm={12} xl={6}>
          <Card className="ab-card" size="small">
            <div className="ab-kpi-title"><QuestionCircleOutlined />监控用户提问</div>
            <div className="ab-kpi-value">{runs.length || "—"}<span style={{ fontSize: 14, color: "#9aa0ac" }}> 题</span></div>
            <div className="ab-kpi-sub">计入指标 {m.n_valid}/{m.n_expected}（带品牌名的题不计入）</div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card className="ab-card" size="small"
            title={<Space>品牌趋势<Switch size="small" checked={showCompetitors} onChange={setShowCompetitors} />
              <Typography.Text type="secondary" style={{ fontWeight: 400 }}>竞品对比</Typography.Text></Space>}
            extra={<Segmented size="small" value={metric} onChange={(v) => setMetric(v as Metric)}
              options={(Object.keys(METRICS) as Metric[]).map((k) => ({ value: k, label: METRICS[k].label }))} />}>
            <EChart option={trendOption} height={300} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>近 30 天每日值；断开处为缺数据或自检未通过</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card className="ab-card" size="small" title="竞品对比" extra={<Tag color="purple">{METRICS[metric].label}</Tag>}>
            <div style={{ background: "#F7F8FB", borderRadius: 8, padding: "8px 12px", marginBottom: 8, fontSize: 13 }}>
              澳觅：<b style={{ color: "#5B5CF6" }}>{barBlocked || m.n_valid === 0 ? "—" : `三家中${aomiTied ? "并列" : ""}第 ${aomiRank}`}</b>
              <span style={{ margin: "0 10px", color: "#ddd" }}>|</span>最新 {cell(m, metric, "aomi")}
              <span style={{ margin: "0 10px", color: "#ddd" }}>|</span>前一天 {prev ? formatRatio(prev[metric].aomi) : "无数据"}
            </div>
            {barBlocked ? <Alert type="error" message="自检未通过，不出数" /> : <EChart option={barOption} height={200} />}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card className="ab-card" size="small" title="分场景" extra={<Tag color="purple">{METRICS[metric].label}</Tag>}>
            <Table size="small" pagination={false} rowKey="scene" dataSource={data.by_scene} scroll={{ x: 560 }}
              columns={[
                { title: "场景", dataIndex: "scene" },
                { title: "有效/应采", width: 90, render: (_, s) => `${s.metrics.n_valid}/${s.metrics.n_expected}` },
                ...ENTITIES.map((e) => ({ title: ENTITY_NAME[e], key: e, render: (_: unknown, s: { metrics: DailyMetrics }) => cell(s.metrics, metric, e) })),
              ]} />
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card className="ab-card" size="small" title={`采集与消耗（${dayWord}）`}>
            <Descriptions column={1} size="small">
              <Descriptions.Item label="采集任务">
                {data.job ? <Tag color={JOB_TAG[data.job.status]?.color}>{JOB_TAG[data.job.status]?.text ?? data.job.status}</Tag> : <Tag>无记录</Tag>}
                {data.job && <span className="num">成功 {data.job.n_ok} / 失败 {data.job.n_failed}</span>}
              </Descriptions.Item>
              {data.job?.message && <Descriptions.Item label="说明">{data.job.message}</Descriptions.Item>}
              <Descriptions.Item label="计费搜索">{data.usage.billed_searches} 次</Descriptions.Item>
              <Descriptions.Item label="token">输入 {data.usage.input_tokens.toLocaleString()} / 输出 {data.usage.output_tokens.toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label="估算费用">
                {data.usage.est_cost_yuan === null ? <Typography.Text type="secondary">未配置单价</Typography.Text> : `¥${data.usage.est_cost_yuan.toFixed(2)}`}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </Col>
      </Row>

      <Card className="ab-card" size="small" title="逐题结果" extra={<Typography.Text type="secondary">点一行查看回答原文和信源</Typography.Text>}>
        <Table<RunItem> size="small" rowKey="run_id" pagination={false} dataSource={runs} scroll={{ x: 900 }}
          rowClassName={() => "ab-clickable-row"} onRow={(r) => ({ onClick: () => nav(`/runs?run=${encodeURIComponent(r.run_id)}`) })}
          columns={[
            { title: "题目", width: 300, render: (_, r) => <span><b>{r.qid}</b> {r.question}</span> },
            { title: "场景", dataIndex: "scene", width: 150, render: (s, r) => (
              <Space size={4} wrap>{s}{data.by_scene.some((sc) => sc.qids.includes(r.qid)) ? null : <Tag>带品牌名·不计入</Tag>}</Space>) },
            { title: "状态", dataIndex: "status", width: 70, render: (s) => <Tag color={s === "valid" ? "green" : s === "failed" ? "red" : "default"}>{s}</Tag> },
            { title: "三家先后", width: 170, render: (_, r) => orderText(r.order) },
            { title: "澳觅提及摘要", dataIndex: "aomi_snippet", render: (s) => (s ? plainSnippet(s) : <Typography.Text type="secondary">未提及</Typography.Text>) },
            { title: "信源", dataIndex: "sources_count", width: 56 },
          ]} />
      </Card>
    </Space>
  );
}
