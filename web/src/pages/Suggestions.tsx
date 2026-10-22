import { useEffect, useState } from "react";
import { Alert, Button, Card, Col, Empty, List, Row, Space, Spin, Tag, Tooltip, Typography } from "antd";
import { get } from "../api";
import { usePlatform } from "../platform";
import { platformLabel, weakReasons } from "../format";
import type { PlatformCount, RefArticle, WeakQuestion } from "../types";

interface Item { weak: WeakQuestion; platforms: PlatformCount[]; references: RefArticle[] }
interface Resp { channel: string; date: string; notice: string; items: Item[] }

export default function Suggestions() {
  const [data, setData] = useState<Resp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const platform = usePlatform();
  useEffect(() => {
    let stale = false;
    get<Resp>("/suggestions", { platform }).then((d) => !stale && setData(d))
      .catch((e) => !stale && setError(String(e.message || e)));
    return () => { stale = true; };
  }, [platform]);
  if (error) return <Alert type="error" showIcon message={error} />;
  if (!data) return <Spin />;
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert type="info" showIcon message={data.notice}
        description={`短板题：不带品牌名的题，最近若干次采集里澳觅提及不到一半，或 mFood/闪蜂排第一的次数多于澳觅（截至 ${data.date}，阈值在"设置"里调）。`} />
      {data.items.length === 0 && <Card className="ab-card"><Empty description="目前没有短板题" /></Card>}
      {data.items.map(({ weak, platforms, references }) => (
        <Card className="ab-card" key={weak.qid} size="small"
          title={<Space><b>{weak.qid}</b>{weak.text}</Space>}
          extra={<Tooltip title="第二阶段：基于知识库生成文章"><Button disabled>写文章</Button></Tooltip>}>
          <Space wrap style={{ marginBottom: 12 }}>
            {weakReasons(weak).map((r) => <Tag color="red" key={r}>{r}</Tag>)}
            <Typography.Text type="secondary">基于最近 {weak.n_runs} 次有效采集</Typography.Text>
          </Space>
          <Row gutter={16}>
            <Col xs={24} lg={10}>
              <Typography.Text strong>平台推荐（按这道题的信源被引用次数）</Typography.Text>
              <List size="small" dataSource={platforms} renderItem={(p, i) => (
                <List.Item><Space><Tag color={p.verified ? "purple" : "default"}>{i + 1}</Tag>{platformLabel(p)}</Space></List.Item>
              )} />
            </Col>
            <Col xs={24} lg={14}>
              <Typography.Text strong>参照文章（被引用最多的）</Typography.Text>
              <List size="small" dataSource={references} locale={{ emptyText: "没有信源" }} renderItem={(a) => (
                <List.Item>
                  <Space wrap>
                    <a href={a.url} target="_blank" rel="noreferrer">{a.title || a.url}</a>
                    <Typography.Text type="secondary">{a.domain}</Typography.Text>
                    <Tag>{a.count} 次</Tag>
                    {a.external_geo && <Tag color="orange">外部 GEO 文章</Tag>}
                  </Space>
                </List.Item>
              )} />
            </Col>
          </Row>
        </Card>
      ))}
    </Space>
  );
}
