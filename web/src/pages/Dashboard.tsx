import { useEffect, useMemo, useState } from "react";
import { Alert, Card, Col, DatePicker, Descriptions, Row, Space, Spin, Table, Tag, Tooltip, Typography } from "antd";
import dayjs from "dayjs";
import { get } from "../api";
import EChart from "../EChart";
import { formatRatio, pct, selfcheckReason, type Metric } from "../format";
import { ENTITIES, ENTITY_NAME, type DailyMetrics, type DashboardData, type Entity } from "../types";

const METRICS: { key: Metric; label: string; hint: string }[] = [
  { key: "mention", label: "提及率", hint: "提到该平台的回答数 / 当天有效回答数（只算不带品牌名的题）" },
  { key: "first", label: "三家中首位率", hint: "只在澳觅、mFood、闪蜂三家之间比先后：排第一的回答数 / 有效回答数。Klook 等其他平台不参与排序" },
  { key: "share", label: "提及份额", hint: "该平台被提及次数 / 三家被提及次数之和" },
];
const COLORS: Record<Entity, string> = { aomi: "#1f6feb", mfood: "#d97706", shanfeng: "#16a34a" };

const JOB_TAG: Record<string, { color: string; text: string }> = {
  done: { color: "green", text: "完成" },
  failed: { color: "red", text: "失败" },
  running: { color: "blue", text: "运行中" },
  requested: { color: "gold", text: "排队中" },
};

export default function Dashboard() {
  const [date, setDate] = useState<string | undefined>();
  const [data, setData] = useState<DashboardData | null>(null);
  const [trend, setTrend] = useState<DailyMetrics[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    get<DashboardData>("/dashboard", { date })
      .then((d) => {
        setData(d);
        setError(null);
        const end = dayjs(d.date);
        return get<DailyMetrics[]>("/dashboard/trend", {
          start: end.subtract(29, "day").format("YYYY-MM-DD"), end: d.date, channel: d.channel,
        }).then(setTrend);
      })
      .catch((e) => setError(String(e.message || e)));
  }, [date]);

  const trendOption = useMemo(() => ({
    tooltip: {
      trigger: "axis" as const,
      formatter: (params: unknown) => {
        const ps = params as { axisValue: string; dataIndex: number }[];
        const day = trend[ps[0].dataIndex];
        const lines = ENTITIES.map((e) => `${ENTITY_NAME[e]}：${formatRatio(day.mention[e])}`);
        return [`${ps[0].axisValue}${day.n_valid === 0 ? "（缺数据）" : ""}`, ...lines].join("<br/>");
      },
    },
    legend: { data: ENTITIES.map((e) => ENTITY_NAME[e]) },
    grid: { left: 40, right: 20, top: 40, bottom: 30 },
    xAxis: { type: "category" as const, data: trend.map((t) => t.date.slice(5)) },
    yAxis: { type: "value" as const, min: 0, max: 100, axisLabel: { formatter: "{value}%" } },
    // 没有数据的日期值为 null，折线在那里断开，不连线
    series: ENTITIES.map((e) => ({
      // showAllSymbol：前后都缺数据的孤立日期只剩一个点，不强制画点就看不见
      name: ENTITY_NAME[e], type: "line" as const, connectNulls: false, showAllSymbol: true, symbolSize: 6,
      itemStyle: { color: COLORS[e] }, data: trend.map((t) => pct(t.mention[e])),
    })),
  }), [trend]);

  if (error) return <Alert type="error" message={error} showIcon />;
  if (!data) return <Spin />;
  const m = data.metrics;
  const isToday = data.date === dayjs().format("YYYY-MM-DD");
  const dayWord = isToday ? "今天" : data.date;

  const rows = METRICS;
  const columns = [
    {
      title: "指标", dataIndex: "label", width: 130,
      render: (_: string, r: (typeof rows)[number]) => (
        <Tooltip title={r.hint}><b style={{ whiteSpace: "nowrap" }}>{r.label}</b></Tooltip>
      ),
    },
    ...ENTITIES.map((e) => ({
      title: ENTITY_NAME[e], key: e,
      render: (_: unknown, r: (typeof rows)[number]) => {
        const reason = selfcheckReason(m.selfcheck_failures, r.key, e);
        return reason
          ? <Typography.Text type="danger">自检未通过：{reason}</Typography.Text>
          : <span className="num" style={{ fontSize: 16, whiteSpace: "nowrap" }}>{formatRatio(m[r.key][e])}</span>;
      },
    })),
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>看板</Typography.Title>
        <DatePicker allowClear={false} value={dayjs(data.date)} onChange={(d) => d && setDate(d.format("YYYY-MM-DD"))}
          disabledDate={(d) => d.isAfter(dayjs(), "day")} />
        <Tag color="blue">{data.channel}</Tag>
        <Typography.Text type="secondary">API 渠道（方舟模型 + 字节搜索），不是豆包 App 的表现</Typography.Text>
        {data.latest_date && data.latest_date !== data.date && (
          <Typography.Link onClick={() => setDate(data.latest_date!)}>回到最近一天 {data.latest_date}</Typography.Link>
        )}
      </Space>

      {m.missing_qids.length > 0 && (
        <Alert type="warning" showIcon
          message={m.n_valid === 0
            ? `${dayWord}没有有效数据（应采 ${m.n_expected} 题）`
            : `${dayWord}只采到 ${m.n_valid}/${m.n_expected} 题，缺：${m.missing_qids.join("、")}`} />
      )}

      <Row gutter={16}>
        <Col xs={24} lg={16}>
          <Card title={`三家对比（${data.date}，不带品牌名的 ${m.n_expected} 题，有效 ${m.n_valid} 题）`} size="small">
            <Table size="middle" pagination={false} rowKey="key" dataSource={rows} columns={columns} scroll={{ x: 520 }} />
          </Card>
        </Col>
        <Col xs={24} lg={8}>
          <Space direction="vertical" size={16} style={{ width: "100%" }}>
            <Card title="采集状态" size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="任务">
                  {data.job ? <Tag color={JOB_TAG[data.job.status]?.color}>{JOB_TAG[data.job.status]?.text ?? data.job.status}</Tag>
                    : <Tag>无记录</Tag>}
                </Descriptions.Item>
                {data.job && <Descriptions.Item label="成功 / 失败">{data.job.n_ok} / {data.job.n_failed}</Descriptions.Item>}
                {data.job?.message && <Descriptions.Item label="说明">{data.job.message}</Descriptions.Item>}
                <Descriptions.Item label="计入指标">
                  {m.n_valid}/{m.n_expected} 题{m.missing_qids.length ? `（缺 ${m.missing_qids.length}）` : ""}
                </Descriptions.Item>
              </Descriptions>
            </Card>
            <Card title={`${dayWord}消耗`} size="small">
              <Descriptions column={1} size="small">
                <Descriptions.Item label="计费搜索">{data.usage.billed_searches} 次</Descriptions.Item>
                <Descriptions.Item label="token">
                  输入 {data.usage.input_tokens.toLocaleString()} / 输出 {data.usage.output_tokens.toLocaleString()}
                </Descriptions.Item>
                <Descriptions.Item label="估算费用">
                  {data.usage.est_cost_yuan === null ? <Typography.Text type="secondary">未配置单价</Typography.Text>
                    : `¥${data.usage.est_cost_yuan.toFixed(2)}`}
                </Descriptions.Item>
              </Descriptions>
            </Card>
          </Space>
        </Col>
      </Row>

      <Card title="每日提及率（近 30 天，断开处为缺数据）" size="small">
        <EChart option={trendOption} height={320} />
      </Card>
    </Space>
  );
}
