import { useCallback, useEffect, useRef, useState } from "react";
import {
  Alert, Button, Card, DatePicker, Drawer, Empty, Input, List, Popconfirm, Progress, Radio, Space, Switch, Table,
  Tag, Tooltip, Typography, message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { get, send } from "../api";
import { cstToday } from "../format";
import { uploadInParts } from "../upload";
import type { KbDoc, KbDocDetail, KbHit, KbProcessStatus } from "../types";

const fail = (e: unknown) => message.error(String((e as Error).message || e));
const mb = (n: number) => (n / 1024 / 1024).toFixed(1);
const BUSY: KbProcessStatus[] = ["queued", "processing"];

function processTag(d: KbDoc) {
  switch (d.process_status) {
    case "uploading": return <Tag>上传中</Tag>;
    case "queued": return <Tag color="blue">排队</Tag>;
    case "processing": return <Tag color="processing">处理中 {d.n_embedded}/{d.n_chunks}</Tag>;
    case "ready": return <Tag color="success">已完成</Tag>;
    case "failed": return <Tooltip title={d.message || "未知原因"}><Tag color="error">失败</Tag></Tooltip>;
  }
}

function Upload({ onDone }: { onDone: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [date, setDate] = useState<Dayjs>(dayjs(cstToday()));
  const [status, setStatus] = useState<"active" | "inactive">("active");
  const [sent, setSent] = useState<number | null>(null); // null = 没在上传
  const picker = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setTitle(f.name.replace(/\.pdf$/i, ""));
  };
  const start = async () => {
    if (!file) return;
    if (!title.trim()) { message.warning("请填写标题"); return; }
    setSent(0);
    try {
      const { id } = await send<{ id: number }>("POST", "/kb/docs", {
        title: title.trim(), filename: file.name, size_bytes: file.size,
        effective_date: date.format("YYYY-MM-DD"), status,
      });
      await uploadInParts(file, id, { onProgress: setSent });
      message.success("上传完成，已排队处理");
      setFile(null); setTitle("");
      if (picker.current) picker.current.value = "";
    } catch (e) {
      fail(e);
    } finally {
      setSent(null);
      onDone(); // 失败时列表里会留下“失败”的记录，也要刷新
    }
  };
  const uploading = sent !== null;
  return (
    <Card title="上传" size="small">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space wrap>
          <input ref={picker} type="file" accept=".pdf,application/pdf" disabled={uploading}
            onChange={(e) => pick(e.target.files?.[0])} />
          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="标题" maxLength={256}
            style={{ width: 280 }} disabled={uploading} />
          <DatePicker value={date} onChange={(d) => d && setDate(d)} allowClear={false} disabled={uploading} />
          <Radio.Group value={status} onChange={(e) => setStatus(e.target.value)} disabled={uploading}
            options={[{ value: "active", label: "现行" }, { value: "inactive", label: "失效" }]} />
          <Button type="primary" disabled={!file || uploading} loading={uploading} onClick={start}>上传</Button>
        </Space>
        {uploading && file && (
          <div>
            <Progress percent={Math.floor((sent / file.size) * 100)} />
            <Typography.Text type="secondary">已传 {mb(sent)} MB / {mb(file.size)} MB</Typography.Text>
          </div>
        )}
      </Space>
    </Card>
  );
}

function DocDrawer({ id, onClose }: { id: number | null; onClose: () => void }) {
  const [doc, setDoc] = useState<KbDocDetail | null>(null);
  useEffect(() => {
    setDoc(null);
    if (id !== null) get<KbDocDetail>(`/kb/docs/${id}`).then(setDoc).catch(fail);
  }, [id]);
  return (
    <Drawer open={id !== null} onClose={onClose} width={520} title={doc?.title ?? "文档详情"}>
      {doc && (
        <Space direction="vertical" style={{ width: "100%" }}>
          <Alert type="warning" showIcon
            message={`这些页面的内容不会被检索到：${doc.empty_pages.length ? `共 ${doc.empty_pages.length} 页无文字层（红色行）` : "本文档没有无文字层的页面"}`}
            description="不做 OCR，整页没有文字的页面不入库。" />
          <Table size="small" rowKey="page_no" dataSource={doc.pages} pagination={{ pageSize: 50, showSizeChanger: false }}
            onRow={(p) => (p.n_chars === 0 ? { style: { background: "#fff1f0" } } : {})}
            columns={[
              { title: "PDF 页码", dataIndex: "page_no", width: 100 },
              { title: "字数", dataIndex: "n_chars", width: 90 },
              { title: "图片数", dataIndex: "n_images", width: 90 },
              { title: "", render: (_, p) => (p.n_chars === 0 ? <Typography.Text type="danger">无文字层，未入库</Typography.Text> : null) },
            ]} />
        </Space>
      )}
    </Drawer>
  );
}

function Docs({ docs, reload }: { docs: KbDoc[]; reload: () => void }) {
  const [detailId, setDetailId] = useState<number | null>(null);
  const toggle = (d: KbDoc, on: boolean) =>
    send("PATCH", `/kb/docs/${d.id}`, { status: on ? "active" : "inactive" }).then(reload).catch(fail);
  const reprocess = (d: KbDoc) => send("POST", `/kb/docs/${d.id}/reprocess`).then(reload).catch(fail);
  const remove = (d: KbDoc) => send("DELETE", `/kb/docs/${d.id}`).then(reload).catch(fail);
  return (
    <Card title="文档列表" size="small">
      <Table<KbDoc> size="small" rowKey="id" dataSource={docs} pagination={false}
        columns={[
          { title: "标题", dataIndex: "title" },
          { title: "生效日期", dataIndex: "effective_date", width: 110 },
          { title: "状态", width: 80, render: (_, d) => (
            <Tooltip title="现行才会被检索"><Switch size="small" checked={d.status === "active"} onChange={(v) => toggle(d, v)} /></Tooltip>) },
          { title: "处理状态", width: 130, render: (_, d) => processTag(d) },
          { title: "页数", dataIndex: "n_pages", width: 70 },
          { title: "切片数", dataIndex: "n_chunks", width: 80 },
          { title: "无文字页数", width: 100, render: (_, d) => (d.process_status === "ready" ? d.n_empty_pages ?? 0 : "—") },
          { title: "上传时间", width: 160, render: (_, d) => d.created_at.slice(0, 16).replace("T", " ") },
          { title: "操作", width: 200, render: (_, d) => (
            <Space size={4}>
              <Button size="small" type="link" onClick={() => setDetailId(d.id)}>查看</Button>
              <Button size="small" type="link" disabled={!["ready", "failed"].includes(d.process_status)}
                onClick={() => reprocess(d)}>重新处理</Button>
              <Popconfirm title="删除这份文档？" description="文档、切片和 PDF 文件都会删除。" okText="删除" okButtonProps={{ danger: true }}
                onConfirm={() => remove(d)}>
                <Button size="small" type="link" danger>删除</Button>
              </Popconfirm>
            </Space>) },
        ]} />
      <DocDrawer id={detailId} onClose={() => setDetailId(null)} />
    </Card>
  );
}

function SearchTest() {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<KbHit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const run = () => {
    if (!query.trim()) return;
    setLoading(true);
    send<KbHit[]>("POST", "/kb/search", { query: query.trim(), limit: 5 })
      .then(setHits).catch(fail).finally(() => setLoading(false));
  };
  const halfText = (h: KbHit) => (h.half === "L" ? "（左）" : h.half === "R" ? "（右）" : "");
  return (
    <Card title="检索测试" size="small">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Space.Compact style={{ width: "100%", maxWidth: 640 }}>
          <Input value={query} onChange={(e) => setQuery(e.target.value)} onPressEnter={run} placeholder="输入要检索的问题" />
          <Button type="primary" loading={loading} onClick={run}>检索</Button>
        </Space.Compact>
        {hits !== null && (hits.length === 0 ? <Empty description="没有命中" /> : (
          <List dataSource={hits} renderItem={(h) => (
            <List.Item>
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Space wrap>
                  <Typography.Text strong>{h.doc_title}</Typography.Text>
                  <Typography.Text type="secondary">生效 {h.effective_date}</Typography.Text>
                  <a href={`/api/kb/docs/${h.doc_id}/file#page=${h.page_no}`} target="_blank" rel="noreferrer">
                    PDF 第 {h.page_no} 页{halfText(h)}
                  </a>
                  <Tag>语义名次 {h.semantic_rank ?? "—"}</Tag>
                  <Tag>关键词名次 {h.keyword_rank ?? "—"}</Tag>
                </Space>
                <Typography.Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{h.text}</Typography.Paragraph>
              </Space>
            </List.Item>)} />
        ))}
      </Space>
    </Card>
  );
}

export default function Knowledge() {
  const [docs, setDocs] = useState<KbDoc[]>([]);
  const load = useCallback(() => { get<KbDoc[]>("/kb/docs").then(setDocs).catch(fail); }, []);
  useEffect(load, [load]);
  // 有文档在排队或处理中时每 5 秒刷新
  const busy = docs.some((d) => BUSY.includes(d.process_status));
  useEffect(() => {
    if (!busy) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [busy, load]);
  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Upload onDone={load} />
      <Docs docs={docs} reload={load} />
      <SearchTest />
    </Space>
  );
}
