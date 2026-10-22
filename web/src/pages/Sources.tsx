import { useEffect, useState } from "react";
import { Alert, Card, Col, DatePicker, Empty, Row, Select, Space, Table, Tag, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { get } from "../api";
import { usePlatform } from "../platform";
import EChart from "../EChart";
import { cstToday, platformLabel } from "../format";
import type { PlatformCount } from "../types";

interface Owned { run_id: string; rank: number; title: string; url: string; domain: string; platform_key: string | null }

export default function Sources() {
  const platform = usePlatform();
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [dayjs(cstToday()).subtract(29, "day"), dayjs(cstToday())]);
  const [channel, setChannel] = useState<string | undefined>();
  const [domains, setDomains] = useState<[string, number][]>([]);
  const [platforms, setPlatforms] = useState<PlatformCount[]>([]);
  const [owned, setOwned] = useState<Owned[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    const p = { start: range[0].format("YYYY-MM-DD"), end: range[1].format("YYYY-MM-DD"), channel, platform };
    Promise.all([
      get<[string, number][]>("/sources/domains", p), get<PlatformCount[]>("/sources/platforms", p), get<Owned[]>("/sources/owned", p),
    ]).then(([d, pl, o]) => {
      if (stale) return;
      setDomains(d); setPlatforms(pl); setOwned(o); setError(null);
    }).catch((e) => !stale && setError(String(e.message || e)));
    return () => { stale = true; };
  }, [range, channel, platform]);

  const option = {
    grid: { left: 110, right: 40, top: 10, bottom: 24 },
    xAxis: { type: "value" as const, minInterval: 1 },
    yAxis: { type: "category" as const, inverse: true, data: platforms.map(platformLabel) },
    series: [{ type: "bar" as const, barWidth: 18, label: { show: true, position: "right" as const },
      data: platforms.map((p) => ({ value: p.count, itemStyle: { color: p.verified ? "#5B5CF6" : "#D9DCE3", borderRadius: 4 } })) }],
  };

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space wrap>
        <DatePicker.RangePicker allowClear={false} value={range} onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} />
        <Select allowClear placeholder="渠道（默认设置里的渠道）" style={{ width: 220 }} value={channel} onChange={setChannel}
          options={[{ value: "api-custom" }, { value: "api-plugin" }]} />
        <Typography.Text type="secondary">只统计每日采集（round=daily）里有效回答的信源</Typography.Text>
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      <Row gutter={[16, 16]}>
        <Col xs={24} xl={12}>
          <Card className="ab-card" size="small" title="7 个可发布平台的被引用次数"
            extra={<Typography.Text type="secondary">0 次 = 未验证</Typography.Text>}>
            <EChart option={option} height={300} />
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card className="ab-card" size="small" title="域名排行（m. / www. 合并）">
            <Table size="small" rowKey={(r) => r[0]} dataSource={domains} pagination={{ pageSize: 10, showSizeChanger: false }}
              columns={[
                { title: "#", width: 50, render: (_, __, i) => i + 1 },
                { title: "域名", render: (_, r) => r[0] },
                { title: "被引用次数", width: 110, render: (_, r) => r[1] },
              ]} />
          </Card>
        </Col>
      </Row>
      <Card className="ab-card" size="small" title={`自有内容被引用（${owned.length}）`}
        extra={<Typography.Text type="secondary">自有渠道前缀在"设置"里维护</Typography.Text>}>
        {owned.length === 0 ? <Empty description="这段时间没有自有内容被引用（或还没配置自有渠道前缀）" /> : (
          <Table<Owned> size="small" rowKey={(r) => `${r.run_id}-${r.rank}`} dataSource={owned} pagination={false}
            columns={[
              { title: "标题", render: (_, r) => <a href={r.url} target="_blank" rel="noreferrer">{r.title || r.url}</a> },
              { title: "域名", dataIndex: "domain", width: 200 },
              { title: "平台", dataIndex: "platform_key", width: 100, render: (v) => (v ? <Tag>{v}</Tag> : "—") },
              { title: "所在回答", dataIndex: "run_id", width: 300, render: (v) => <a href={`/runs?run=${encodeURIComponent(v)}`}>{v}</a> },
            ]} />
        )}
      </Card>
    </Space>
  );
}
