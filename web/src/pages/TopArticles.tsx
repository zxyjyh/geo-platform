import { useEffect, useState } from "react";
import { Alert, Card, DatePicker, Progress, Space, Table, Typography } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { get } from "../api";
import { usePlatform } from "../platform";
import { cstToday } from "../format";
import type { TopArticle } from "../types";

export default function TopArticles() {
  const platform = usePlatform();
  const [range, setRange] = useState<[Dayjs, Dayjs]>(() => [dayjs(cstToday()).subtract(29, "day"), dayjs(cstToday())]);
  const [articles, setArticles] = useState<TopArticle[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let stale = false;
    setLoading(true);
    const params = { start: range[0].format("YYYY-MM-DD"), end: range[1].format("YYYY-MM-DD"), platform };
    get<{ articles: TopArticle[] }>("/sources/top-articles", params)
      .then((res) => {
        if (stale) return;
        setArticles(res.articles);
        setError(null);
      })
      .catch((e) => !stale && setError(String(e.message || e)))
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [range, platform]);

  const maxCount = articles.length > 0 ? articles[0].citation_count : 1;

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Space wrap>
        <DatePicker.RangePicker allowClear={false} value={range}
          onChange={(v) => v && v[0] && v[1] && setRange([v[0], v[1]])} />
        <Typography.Text type="secondary">
          按标准化 URL 聚合，统计每日有效回答中的信源引用次数
        </Typography.Text>
      </Space>
      {error && <Alert type="error" showIcon message={error} />}
      <Card className="ab-card" size="small" title={`热门引用文章 Top ${articles.length}`}>
        <Table<TopArticle>
          size="small"
          rowKey="url"
          dataSource={articles}
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          columns={[
            {
              title: "#", width: 60,
              render: (_, __, i) => i + 1,
            },
            {
              title: "标题", ellipsis: true,
              render: (_, r) => (
                <a href={r.url} target="_blank" rel="noreferrer">
                  {r.title || r.url}
                </a>
              ),
            },
            { title: "域名", dataIndex: "domain", width: 160, ellipsis: true },
            {
              title: "引用次数", dataIndex: "citation_count", width: 180,
              sorter: (a, b) => a.citation_count - b.citation_count,
              render: (v: number) => (
                <Space size={8}>
                  <Progress
                    percent={Math.round((v / maxCount) * 100)}
                    size="small"
                    style={{ width: 80, marginBottom: 0 }}
                    showInfo={false}
                    strokeColor="#5B5CF6"
                  />
                  <span style={{ fontWeight: 600 }}>{v}</span>
                </Space>
              ),
            },
            {
              title: "首次引用", dataIndex: "first_seen", width: 110,
              render: (v: string) => v.slice(5),
            },
            {
              title: "最近引用", dataIndex: "last_seen", width: 110,
              render: (v: string) => v.slice(5),
            },
          ]}
        />
      </Card>
    </Space>
  );
}
