import { useEffect, useState } from "react";
import { Card, DatePicker, Space, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { get } from "../api";
import { usePlatform } from "../platform";
import { ENTITY_NAME, type Entity, type PositioningData } from "../types";

const BRAND_COLORS: Record<Entity, string> = {
  aomi: "#5B5CF6",
  mfood: "#E8590C",
  shanfeng: "#12B886",
};

function rankStyle(rank: number | null): React.CSSProperties {
  if (rank === null) return { color: "#999" };
  if (rank === 1) return { backgroundColor: "#d4edda", fontWeight: 600, borderRadius: 4, padding: "2px 8px" };
  if (rank <= 3) return { backgroundColor: "#d1ecf1", borderRadius: 4, padding: "2px 8px" };
  return { backgroundColor: "#e9ecef", color: "#6c757d", borderRadius: 4, padding: "2px 8px" };
}

interface RowData {
  qid: string;
  text: string;
  scene: string;
  [key: string]: string | number | null;
}

export default function Positioning() {
  const platform = usePlatform();
  const [date, setDate] = useState<string>(dayjs().format("YYYY-MM-DD"));
  const [data, setData] = useState<PositioningData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let stale = false;
    setLoading(true);
    get<PositioningData>("/dashboard/positioning", { date, platform })
      .then((d) => { if (!stale) setData(d); })
      .catch(console.error)
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [date, platform]);

  const columns: ColumnsType<RowData> = [
    {
      title: "题目",
      dataIndex: "qid",
      width: 320,
      fixed: "left",
      render: (_: unknown, row: RowData) => (
        <div>
          <div style={{ fontWeight: 600, color: "#1f2937" }}>{row.qid}</div>
          <div style={{ fontSize: 12, color: "#6b7280", marginTop: 2 }}>
            {row.text.length > 20 ? row.text.slice(0, 20) + "…" : row.text}
          </div>
        </div>
      ),
    },
    {
      title: "场景",
      dataIndex: "scene",
      width: 80,
      render: (s: string) => s || "—",
    },
    ...(data?.brands || []).map((brand) => ({
      title: (
        <div style={{ textAlign: "center" as const, fontWeight: 600, color: BRAND_COLORS[brand as Entity] }}>
          {ENTITY_NAME[brand as Entity]}
        </div>
      ),
      dataIndex: brand,
      width: 100,
      align: "center" as const,
      render: (rank: number | null) => (
        <span style={rankStyle(rank)}>
          {rank === null ? "—" : rank}
        </span>
      ),
    })),
  ];

  const dataSource: RowData[] = (data?.questions || []).map((q) => ({
    ...q,
    ...(data.matrix[q.qid] || {}),
  }));

  return (
    <Card title="竞品横向占位分布" style={{ maxWidth: 1000 }}>
      <Space style={{ marginBottom: 16 }}>
        <Typography.Text strong>日期：</Typography.Text>
        <DatePicker
          value={dayjs(date)}
          onChange={(d) => d && setDate(d.format("YYYY-MM-DD"))}
          allowClear={false}
        />
        <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
          渠道：{data?.channel || "—"}
        </Typography.Text>
      </Space>
      <Table<RowData>
        loading={loading}
        dataSource={dataSource}
        columns={columns}
        rowKey="qid"
        pagination={false}
        size="small"
        scroll={{ x: 600 }}
      />
    </Card>
  );
}
