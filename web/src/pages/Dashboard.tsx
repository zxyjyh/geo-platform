import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, Collapse, DatePicker, Descriptions, Row, Segmented, Select, Space, Switch, Table, Tag, Tooltip, Typography } from "antd";
import { AimOutlined, PercentageOutlined, QuestionCircleOutlined, TrophyOutlined } from "@ant-design/icons";
import dayjs from "dayjs";
import { useNavigate } from "react-router-dom";
import { get } from "../api";
import { usePlatform } from "../platform";
import EChart from "../EChart";
import { coveredQs, formatRatio, missingNotice, pct, repsChanges, prevText, selfcheckReason, trendValue, type Metric } from "../format";
import { ENTITIES, ENTITY_NAME, type AttributionDay, type DailyMetrics, type DashboardData, type Entity } from "../types";

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

// 品牌趋势与竞品对比并排时等高：卡片撑满列高，柱状图吃掉剩余高度
const FILL_CARD = { width: "100%", display: "flex", flexDirection: "column" } as const;
const FILL_BODY = { flex: 1, display: "flex", flexDirection: "column" } as const;

function cell(m: DailyMetrics | undefined, metric: Metric, e: Entity) {
  if (!m) return <Typography.Text type="secondary">无数据</Typography.Text>;
  const reason = selfcheckReason(m.selfcheck_failures, metric, e);
  return reason ? <Typography.Text type="danger">自检未通过：{reason}</Typography.Text>
    : <span className="num">{formatRatio(m[metric][e])}</span>;
}

function Attribution({ a }: { a: AttributionDay | null }) {
  const nav = useNavigate();
  if (!a) return <Typography.Text type="secondary">加载中…</Typography.Text>;
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Descriptions column={1} size="small">
        <Descriptions.Item label="正文给出官方入口">
          {a.configured ? <span className="num">{formatRatio(a.text)}</span>
            : <span><Typography.Text type="secondary">未配置官方标识</Typography.Text>，<a onClick={() => nav("/settings?tab=marks")}>去设置</a></span>}
        </Descriptions.Item>
        <Descriptions.Item label="信源含自有内容"><span className="num">{formatRatio(a.source)}</span></Descriptions.Item>
      </Descriptions>
      {a.hits.length > 0 && (
        <Collapse size="small" ghost items={[{
          key: "hits", label: `明细（${a.hits.length} 条回答）`,
          children: (
            <Table size="small" pagination={false} rowKey="run_id" dataSource={a.hits}
              rowClassName={() => "ab-clickable-row"} onRow={(h) => ({ onClick: () => nav(`/runs?run=${encodeURIComponent(h.run_id)}`) })}
              columns={[
                { title: "题", dataIndex: "qid", width: 60 },
                { title: "命中的标识", dataIndex: "marks", render: (ms: string[]) => ms.length ? ms.map((m) => <Tag key={m}>{m}</Tag>) : "—" },
                { title: "自有信源", dataIndex: "owned_source", width: 80, render: (v: boolean) => v ? <Tag color="green">有</Tag> : "—" },
              ]} />
          ),
        }]} />
      )}
    </Space>
  );
}

export default function Dashboard() {
  const platform = usePlatform();
  const [query, setQuery] = useState<{ date?: string; channel?: string }>({});
  const [data, setData] = useState<DashboardData | null>(null);
  const [trend, setTrend] = useState<DailyMetrics[]>([]);
  const [attribution, setAttribution] = useState<AttributionDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<Metric>("mention");
  const [showCompetitors, setShowCompetitors] = useState(true);

  useEffect(() => {
    let stale = false; // 快速切换日期时，旧请求晚到不能覆盖新数据
    setError(null);
    setTrend([]); // 换日期/渠道时先清空，免得"前一天"短暂显示旧渠道的数
    setAttribution(null);
    get<DashboardData>("/dashboard", { ...query, platform })
      .then((d) => {
        if (stale) return;
        setData(d);
        const end = dayjs(d.date);
        get<DailyMetrics[]>("/dashboard/trend", { start: end.subtract(29, "day").format("YYYY-MM-DD"), end: d.date, channel: d.channel, platform })
          .then((t) => !stale && setTrend(t))
          .catch((e) => !stale && setError(`趋势加载失败：${e.message}`));
        get<AttributionDay>("/dashboard/attribution", { date: d.date, channel: d.channel, platform })
          .then((a) => !stale && setAttribution(a))
          .catch((e) => !stale && setError(`品牌归因加载失败：${e.message}`));
      })
      .catch((e) => !stale && setError(String(e.message || e)));
    return () => { stale = true; };
  }, [query, platform]);

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
    // 每题次数变了 = 口径变了，在那一天画竖线提示
    series: ENTITIES.filter((e) => e === "aomi" || showCompetitors).map((e, i) => ({
      name: ENTITY_NAME[e], type: "line" as const, smooth: true, connectNulls: false, showAllSymbol: true, symbolSize: 6,
      itemStyle: { color: COLORS[e] }, lineStyle: { width: e === "aomi" ? 2.5 : 1.5, type: e === "aomi" ? "solid" as const : "dashed" as const },
      data: trend.map((t) => trendValue(t, metric, e)),
      ...(i === 0 && {
        markLine: {
          symbol: "none", silent: true, lineStyle: { type: "dashed" as const, color: "#999" },
          data: repsChanges(trend).map((c) => ({ xAxis: c.date.slice(5), label: { formatter: `每题次数改为 ${c.reps}` } })),
        },
      }),
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
      <Card className="ab-card ab-kpi-card" size="small">
        <Tooltip title={METRICS[k].hint}>
          <div className="ab-kpi-title">{METRICS[k].icon} {METRICS[k].label}</div>
        </Tooltip>
        <div className="ab-kpi-value" style={{ fontSize: 36, fontWeight: 700, margin: "12px 0" }}>
          {cell(m, k, "aomi")}
        </div>
        <div className="ab-kpi-sub" style={{ fontSize: 13, color: "#8c8c8c" }}>
          前一天 {prevText(prev, k, "aomi")}
        </div>
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
            一览澳觅在大模型回答里的提及、三家先后与趋势。数据来自 {data.channel}，不是 App 端的表现。
          </Typography.Text></div>
        </Col>
        <Col>
          <Space wrap>
            <Typography.Text type="secondary">筛选：</Typography.Text>
            <DatePicker allowClear={false} value={dayjs(data.date)}
              onChange={(d) => d && setQuery((q) => ({ ...q, date: d.format("YYYY-MM-DD") }))}
              disabledDate={(d) => d.format("YYYY-MM-DD") > data.today} />
            <Select value={data.channel} style={{ width: 130 }} onChange={(c) => setQuery({ ...query, channel: c })}
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
          <Card className="ab-card ab-kpi-card" size="small">
            <div className="ab-kpi-title"><QuestionCircleOutlined /> 监控提问</div>
            <div className="ab-kpi-value" style={{ fontSize: 36, fontWeight: 700, margin: "12px 0" }}>
              {m.n_expected ?? "—"}<span style={{ fontSize: 18, color: "#8c8c8c", fontWeight: 400 }}> 题</span>
            </div>
            <div className="ab-kpi-sub" style={{ fontSize: 13, color: "#8c8c8c" }}>
              计入指标 {m.n_valid}{m.n_reps > 1 ? ` 条回答（每题 ${m.n_reps} 次）` : ""}（带品牌名不计入）
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ display: "flex", flexWrap: "wrap" }}>
        <Col xs={24} xl={15} style={{ display: "flex" }}>
          <Card className="ab-card" size="small" style={FILL_CARD} styles={{ body: FILL_BODY }}
            title={<Space>品牌趋势<Switch size="small" checked={showCompetitors} onChange={setShowCompetitors} />
              <Typography.Text type="secondary" style={{ fontWeight: 400 }}>竞品对比</Typography.Text></Space>}
            extra={<Segmented size="small" value={metric} onChange={(v) => setMetric(v as Metric)}
              options={(Object.keys(METRICS) as Metric[]).map((k) => ({ value: k, label: METRICS[k].label }))} />}>
            <EChart option={trendOption} height={300} />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>近 30 天每日值；断开处为缺数据或自检未通过</Typography.Text>
          </Card>
        </Col>
        <Col xs={24} xl={9} style={{ display: "flex" }}>
          <Card className="ab-card" size="small" style={FILL_CARD} styles={{ body: FILL_BODY }} title="竞品对比" extra={<Tag color="purple">{METRICS[metric].label}</Tag>}>
            <div style={{ background: "#F7F8FB", borderRadius: 8, padding: "8px 12px", marginBottom: 8, fontSize: 13 }}>
              澳觅：<b style={{ color: "#5B5CF6" }}>{barBlocked || m.n_valid === 0 ? "—" : `三家中${aomiTied ? "并列" : ""}第 ${aomiRank}`}</b>
              <span style={{ margin: "0 10px", color: "#ddd" }}>|</span>最新 {cell(m, metric, "aomi")}
              <span style={{ margin: "0 10px", color: "#ddd" }}>|</span>前一天 {prevText(prev, metric, "aomi")}
            </div>
            {barBlocked ? <Alert type="error" message="自检未通过，不出数" /> : <div style={{ flex: 1, minHeight: 200 }}><EChart option={barOption} height="100%" /></div>}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={15}>
          <Card className="ab-card" size="small" title="分场景" extra={<Tag color="purple">{METRICS[metric].label}</Tag>}>
            <Table size="small" pagination={false} rowKey="scene" dataSource={data.by_scene} scroll={{ x: 560 }}
              columns={[
                { title: "场景", dataIndex: "scene" },
                { title: "有效/应采", width: 90, render: (_, s) => `${coveredQs(s.metrics)}/${s.metrics.n_expected}` },
                ...ENTITIES.map((e) => ({ title: ENTITY_NAME[e], key: e, render: (_: unknown, s: { metrics: DailyMetrics }) => cell(s.metrics, metric, e) })),
              ]} />
          </Card>
        </Col>
        <Col xs={24} xl={9}>
          <Card className="ab-card" size="small" title={`品牌归因（${dayWord}）`} style={{ marginBottom: 16 }}
            extra={<Tooltip title="全部题（含带品牌名的）中提到澳觅的回答里：正文有没有给出官网、客服电话等官方入口；信源里有没有澳觅自有内容">
              <QuestionCircleOutlined /></Tooltip>}>
            <Attribution a={attribution} />
          </Card>
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

    </Space>
  );
}
