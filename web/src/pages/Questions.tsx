import { useEffect, useState } from "react";
import { Card, Table, Tag, Typography } from "antd";
import { get } from "../api";

interface Q { qid: string; version: string; text: string; branded: boolean; scene: string; intent: string; status: string }

export default function Questions() {
  const [qs, setQs] = useState<Q[] | null>(null);
  useEffect(() => { get<Q[]>("/questions").then(setQs); }, []);
  return (
    <Card className="ab-card" size="small" title="用户提问"
      extra={<Typography.Text type="secondary">只读；改题要升题库版本（data/questions/questions-v*.csv）</Typography.Text>}>
      <Table<Q> size="middle" rowKey="qid" loading={!qs} dataSource={qs ?? []} pagination={false}
        columns={[
          { title: "编号", dataIndex: "qid", width: 70 },
          { title: "题目", dataIndex: "text" },
          { title: "带品牌名", dataIndex: "branded", width: 160,
            render: (b) => (b ? <Tag color="orange">是 · 不计入提及率</Tag> : <Tag color="purple">否</Tag>) },
          { title: "场景", dataIndex: "scene", width: 180 },
          { title: "意图", dataIndex: "intent", width: 80 },
          { title: "版本", dataIndex: "version", width: 70, render: (v, q) => <span>{v} <Tag>{q.status}</Tag></span> },
        ]} />
    </Card>
  );
}
