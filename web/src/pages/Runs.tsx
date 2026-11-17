import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, Card, Col, DatePicker, Descriptions, Empty, Row, Select, Space, Spin, Switch, Table, Tag, Typography, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { get, send } from "../api";
import { usePlatform } from "../platform";
import { highlightSegments, plainSnippet } from "../format";
import { orderText, type Entity, type RunItem } from "../types";

interface SourceRow {
  rank: number; title: string; url: string; url_norm: string; domain: string; site_name: string;
  publish_time_raw: string; platform_key: string | null; is_owned: boolean; external_geo: boolean;
}
interface RunDetail {
  run_id: string; collect_date: string; collected_at: string; qid: string; question: string | null; round: string;
  channel: string; status: string; error: string | null; answer_text: string; search_queries: string;
  billed_searches: number | null; coding: { alias_version: number; mention: Record<Entity, boolean>; order: Record<Entity, number | null> } | null;
  sources: SourceRow[];
}

const HL: Record<Entity, string> = { aomi: "#E0E1FF", mfood: "#FFE3CC", shanfeng: "#C9F2E3" };
const STATUS: Record<string, string> = { valid: "green", void: "default", failed: "red" };

function Detail({ runId, aliases }: { runId: string; aliases: Record<Entity, string[]> | null }) {
  const [d, setD] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    // 先点 A 再点 B：A 的响应晚到不能盖住 B，否则右侧显示 A、打标签也会打到 A 的信源上
    let stale = false;
    setD(null);
    setError(null);
    get<RunDetail>(`/runs/${encodeURIComponent(runId)}`)
      .then((r) => !stale && setD(r))
      .catch((e) => !stale && setError(e.status === 404 ? `没有这条回答：${runId}` : String(e.message || e)));
    return () => { stale = true; };
  }, [runId, reload]);

  const toggleGeo = async (s: SourceRow, on: boolean) => {
    try {
      if (on) await send("POST", "/sources/tags", { url: s.url, tag: "external_geo", note: "" });
      else await send("DELETE", `/sources/tags?url=${encodeURIComponent(s.url)}`);
      setReload((n) => n + 1);
    } catch (e) {
      message.error(String((e as Error).message));
    }
  };

  if (error) return <Alert type="error" showIcon message={error} />;
  if (!d) return <Spin />;
  const segs = aliases ? highlightSegments(d.answer_text, aliases) : [{ text: d.answer_text, entity: null }];
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="题目" span={2}>{d.qid} {d.question}</Descriptions.Item>
        <Descriptions.Item label="日期">{d.collect_date}</Descriptions.Item>
        <Descriptions.Item label="采集时间">{d.collected_at.replace("T", " ").slice(0, 19)}</Descriptions.Item>
        <Descriptions.Item label="渠道">{d.channel}（{d.round}）</Descriptions.Item>
        <Descriptions.Item label="状态"><Tag color={STATUS[d.status]}>{d.status}</Tag></Descriptions.Item>
        <Descriptions.Item label="三家先后" span={2}>
          {orderText(d.coding?.order ?? null)}
          {d.coding && <Typography.Text type="secondary">（别名表 v{d.coding.alias_version}）</Typography.Text>}
        </Descriptions.Item>
        <Descriptions.Item label="搜索词" span={2}>{d.search_queries || "—"}</Descriptions.Item>
      </Descriptions>
      {d.error && <Alert type="error" message={d.error} />}
      <Card size="small" title="回答原文">
        <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.8, maxHeight: 420, overflow: "auto" }}>
          {segs.length ? segs.map((s, i) => s.entity
            ? <mark key={i} style={{ background: HL[s.entity], padding: "0 2px" }}>{s.text}</mark>
            : <span key={i}>{s.text}</span>) : <Typography.Text type="secondary">（空）</Typography.Text>}
        </div>
      </Card>
      <Card size="small" title={`信源（${d.sources.length}）`}>
        <Table<SourceRow> size="small" rowKey="rank" pagination={false} dataSource={d.sources} scroll={{ x: 700 }}
          columns={[
            { title: "#", dataIndex: "rank", width: 40 },
            { title: "标题", dataIndex: "title", render: (t, s) => <a href={s.url} target="_blank" rel="noreferrer">{t || s.url}</a> },
            { title: "站点", dataIndex: "site_name", width: 110, render: (v, s) => v || s.domain },
            { title: "平台", dataIndex: "platform_key", width: 90, render: (v) => v ? <Tag>{v}</Tag> : "—" },
            { title: "自有", dataIndex: "is_owned", width: 60, render: (v) => v ? <Tag color="green">是</Tag> : "—" },
            { title: "外部 GEO", dataIndex: "external_geo", width: 90,
              render: (v, s) => <Switch size="small" checked={v} onChange={(on) => toggleGeo(s, on)} /> },
          ]} />
      </Card>
    </Space>
  );
}

export default function Runs() {
  const platform = usePlatform();
  const today = dayjs();
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>([today, today]);
  const [filters, setFilters] = useState<Record<string, string | undefined>>({ round: "daily" });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; items: RunItem[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [params, setParams] = useSearchParams();
  const selected = params.get("run");
  const setSelected = (id: string) => setParams((p) => { p.set("run", id); return p; });
  const [questions, setQuestions] = useState<{ qid: string; text: string }[]>([]);
  const [aliases, setAliases] = useState<Record<Entity, string[]> | null>(null);

  useEffect(() => {
    // 这两个只影响筛选项和高亮，失败时页面照常可用，只提示
    get<{ qid: string; text: string }[]>("/questions").then(setQuestions).catch(() => message.warning("题目列表加载失败"));
    get<Record<Entity, string[]>>("/settings/aliases").then(setAliases).catch(() => message.warning("别名表加载失败，原文不高亮"));
  }, []);
  useEffect(() => {
    // 快速翻页或改筛选：只接受最后一次请求的结果
    let stale = false;
    setLoading(true);
    setError(null);
    get<{ total: number; items: RunItem[] }>("/runs", {
      ...filters, platform, page, size: 20,
      date_from: range?.[0]?.format("YYYY-MM-DD"), date_to: range?.[1]?.format("YYYY-MM-DD"),
    })
      .then((r) => {
        if (stale) return;
        setData(r);
        // 如果有数据但没有选中任何回答，自动选中第一条
        if (r.items.length > 0 && !selected) {
          setSelected(r.items[0].run_id);
        }
      })
      .catch((e) => !stale && (setData(null), setError(String(e.message || e))))
      .finally(() => !stale && setLoading(false));
    return () => { stale = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, page, range, platform]);

  const setF = (k: string) => (v: string | undefined) => {
    setPage(1);
    setFilters((f) => ({ ...f, [k]: v }));
  };

  return (
    <Row gutter={16}>
      <Col xs={24} xl={10}>
        <Card className="ab-card" size="small" title="大模型回答记录">
          <Space wrap style={{ marginBottom: 12 }}>
            <DatePicker.RangePicker value={range} onChange={(v) => { setPage(1); setRange(v); }} />
            <Select allowClear placeholder="题目" style={{ width: 110 }} value={filters.qid} onChange={setF("qid")}
              options={questions.map((q) => ({ value: q.qid, label: q.qid, title: q.text }))} />
            <Select allowClear placeholder="渠道" style={{ width: 120 }} value={filters.channel} onChange={setF("channel")}
              options={[{ value: "api-custom" }, { value: "api-plugin" }]} />
            <Select allowClear placeholder="轮次" style={{ width: 100 }} value={filters.round} onChange={setF("round")}
              options={[{ value: "daily", label: "每日" }, { value: "trial", label: "试跑" }]} />
            <Select allowClear placeholder="提到澳觅" style={{ width: 110 }} value={filters.aomi_mentioned} onChange={setF("aomi_mentioned")}
              options={[{ value: "true", label: "提到澳觅" }, { value: "false", label: "没提澳觅" }]} />
            <Select allowClear placeholder="状态" style={{ width: 100 }} value={filters.status} onChange={setF("status")}
              options={[{ value: "valid" }, { value: "void" }, { value: "failed" }]} />
          </Space>
          {error && <Alert type="error" showIcon message={`列表加载失败：${error}`} style={{ marginBottom: 12 }} />}
          <Table<RunItem> size="small" rowKey="run_id" loading={loading} dataSource={data?.items ?? []}
            onRow={(r) => ({ onClick: () => setSelected(r.run_id), style: { cursor: "pointer",
              background: r.run_id === selected ? "#eef4ff" : undefined } })}
            pagination={{ current: page, pageSize: 20, total: data?.total, onChange: setPage, showSizeChanger: false,
              showTotal: (t) => `共 ${t} 条` }}
            columns={[
              { title: "日期", dataIndex: "collect_date", width: 100 },
              { title: "题目", dataIndex: "qid", width: 60, render: (q, r) => <span title={r.question ?? ""}>{q}</span> },
              { title: "状态", dataIndex: "status", width: 70, render: (s) => <Tag color={STATUS[s]}>{s}</Tag> },
              { title: "三家先后", render: (_, r) => (
                <div>{orderText(r.order)}
                  {r.aomi_snippet && <div style={{ color: "#9aa0ac", fontSize: 12 }}>{plainSnippet(r.aomi_snippet)}</div>}</div>) },
              { title: "信源", dataIndex: "sources_count", width: 50 },
            ]} />
        </Card>
      </Col>
      <Col xs={24} xl={14}>
        <Card className="ab-card" size="small" title="回答详情">
          {selected ? <Detail runId={selected} aliases={aliases} /> : <Empty description="点左边一条记录查看回答和信源" />}
        </Card>
      </Col>
    </Row>
  );
}
