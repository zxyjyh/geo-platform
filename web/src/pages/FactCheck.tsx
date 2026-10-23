import { useEffect, useState } from "react";
import {
  Button, Card, Col, DatePicker, Modal, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography, message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { get, send } from "../api";
import type { FactClaim, FactStats } from "../types";

const fail = (e: unknown) => message.error(String((e as Error).message || e));

const DECISION_COLOR: Record<string, string> = {
  pending: "default", confirmed: "success", rejected: "error", new_item: "processing",
};
const DECISION_LABEL: Record<string, string> = {
  pending: "待复核", confirmed: "已确认", rejected: "已驳回", new_item: "加入清单",
};

export default function FactCheck() {
  const [stats, setStats] = useState<FactStats | null>(null);
  const [rows, setRows] = useState<FactClaim[]>([]);
  const [filter, setFilter] = useState<"all" | "known" | "unknown">("all");
  const [date, setDate] = useState<Dayjs | null>(null);
  const [loading, setLoading] = useState(false);
  const [extracting, setExtracting] = useState(false);

  const loadStats = () => get<FactStats>("/factcheck/stats").then(setStats).catch(fail);

  const loadClaims = () => {
    setLoading(true);
    const params: Record<string, string | undefined> = {};
    if (filter !== "all") params.filter = filter;
    if (date) params.date = date.format("YYYY-MM-DD");
    get<FactClaim[]>("/factcheck/claims", params)
      .then(setRows)
      .catch(fail)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadStats(); }, []);
  useEffect(() => { loadClaims(); }, [filter, date]);

  const review = (id: number, decision: string) => {
    send<FactClaim>("POST", `/factcheck/claims/${id}/review`, { reviewer_decision: decision })
      .then(() => { message.success("已更新"); loadStats(); loadClaims(); })
      .catch(fail);
  };

  const extract = () => {
    Modal.confirm({
      title: "触发事实抽取？",
      content: "将对现有回答进行事实一致性抽取，过程不可撤销。",
      onOk: () => {
        setExtracting(true);
        return send<{ count: number }>("POST", "/factcheck/extract")
          .then((r) => { message.success(`抽取完成，共 ${r.count} 条`); loadStats(); loadClaims(); })
          .catch(fail)
          .finally(() => setExtracting(false));
      },
    });
  };

  const columns = [
    {
      title: "原句", dataIndex: "sentence", ellipsis: true,
      render: (v: string) => <Typography.Text style={{ maxWidth: 400 }}>{v}</Typography.Text>,
    },
    {
      title: "事实编号", dataIndex: "fact_code", width: 110,
      render: (v: string | null) => v ? <Tag color="blue">{v}</Tag> : <Typography.Text type="secondary">清单里没有</Typography.Text>,
    },
    {
      title: "判定状态", dataIndex: "reviewer_decision", width: 110,
      render: (v: string) => <Tag color={DECISION_COLOR[v]}>{DECISION_LABEL[v] ?? v}</Tag>,
    },
    {
      title: "备注", dataIndex: "note", width: 160, ellipsis: true,
      render: (v: string) => v || "—",
    },
    {
      title: "操作", width: 240, fixed: "right" as const,
      render: (_: unknown, r: FactClaim) => (
        <Space size={4}>
          <Button size="small" type="link" onClick={() => review(r.id, "confirmed")}>确认</Button>
          <Button size="small" type="link" danger onClick={() => review(r.id, "rejected")}>驳回</Button>
          {r.raw_label === "unknown" && (
            <Button size="small" type="link" onClick={() => review(r.id, "new_item")}>加入清单</Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col span={6}>
          <Card size="small"><Statistic title="总条数" value={stats?.total ?? 0} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="清单匹配（known）" value={stats?.known ?? 0} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="清单里没有（unknown）" value={stats?.unknown ?? 0} /></Card>
        </Col>
        <Col span={6}>
          <Card size="small"><Statistic title="待复核" value={stats?.pending ?? 0} /></Card>
        </Col>
      </Row>

      <Card className="ab-card" size="small">
        <Space style={{ marginBottom: 16 }}>
          <DatePicker
            placeholder="按日期筛选"
            value={date}
            onChange={(d) => setDate(d)}
            allowClear
          />
          <Button type="primary" loading={extracting} onClick={extract}>
            触发抽取
          </Button>
        </Space>
        <Tabs
          activeKey={filter}
          onChange={(k) => setFilter(k as typeof filter)}
          items={[
            { key: "all", label: "全部" },
            { key: "known", label: "清单匹配（known）" },
            { key: "unknown", label: "清单里没有（unknown）" },
          ]}
        />
        <Table<FactClaim>
          rowKey="id"
          size="small"
          dataSource={rows}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: 1000 }}
        />
      </Card>
    </Space>
  );
}
