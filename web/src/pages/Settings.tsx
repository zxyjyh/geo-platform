import { useEffect, useState } from "react";
import {
  Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Typography, message,
} from "antd";
import { useSearchParams } from "react-router-dom";
import { get, send } from "../api";
import { cstToday } from "../format";
import { ENTITIES, ENTITY_NAME, FACT_CATEGORY_LABEL, LINKS_LABEL, MARK_KIND_LABEL, STRICTNESS_LABEL, type BrandMark, type Entity, type FactItem } from "../types";

const fail = (e: unknown) => message.error(String((e as Error).message || e));

function Aliases() {
  const [aliases, setAliases] = useState<Record<Entity, string[]> | null>(null);
  const [version, setVersion] = useState<string>("");
  const load = () => {
    get<Record<Entity, string[]>>("/settings/aliases").then(setAliases);
    get<Record<string, string>>("/settings").then((s) => setVersion(s.alias_version));
  };
  useEffect(load, []);
  if (!aliases) return null;
  const save = () => Modal.confirm({
    title: "保存别名表？",
    content: "会生成新版本的别名表，并用它重算全部历史回答的提及和先后；看板只读最新版本。",
    onOk: () => send<{ version: number; recoded: number }>("PUT", "/settings/aliases", aliases)
      .then((r) => { message.success(`已生成 v${r.version}，重算 ${r.recoded} 条`); load(); }).catch(fail),
  });
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">当前版本 v{version}。字符串匹配，区分大小写：同一个名字的不同写法（繁体、大小写）要分别列出。</Typography.Text>
      {ENTITIES.map((e) => (
        <Form.Item key={e} label={ENTITY_NAME[e]} style={{ marginBottom: 8 }}>
          <Select mode="tags" value={aliases[e]} onChange={(v) => setAliases({ ...aliases, [e]: v })} tokenSeparators={[",", "，"]} />
        </Form.Item>
      ))}
      <Button type="primary" onClick={save}>保存并重算</Button>
    </Space>
  );
}

interface Platform {
  key: string; name: string; domain_suffix: string; publishable: boolean;
  review_strictness: string; allows_links: string; notes: string;
}
const options = (labels: Record<string, string>) => Object.entries(labels).map(([value, label]) => ({ value, label }));

function Platforms() {
  const [rows, setRows] = useState<Platform[]>([]);
  const load = () => get<Platform[]>("/settings/platforms").then(setRows);
  useEffect(() => { load(); }, []);
  const set = (i: number, patch: Partial<Platform>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">域名等于后缀、或以“.后缀”结尾就算这个平台；多个都能匹配时取最长的后缀。保存后重算全部信源。审核宽严、外链、注意事项只在优化建议里展示，不影响平台推荐排序。</Typography.Text>
      <Table<Platform> size="small" rowKey={(_, i) => String(i)} dataSource={rows} pagination={false}
        columns={[
          { title: "key", render: (_, r, i) => <Input value={r.key} onChange={(e) => set(i, { key: e.target.value })} /> },
          { title: "名称", render: (_, r, i) => <Input value={r.name} onChange={(e) => set(i, { name: e.target.value })} /> },
          { title: "域名后缀", render: (_, r, i) => <Input value={r.domain_suffix} onChange={(e) => set(i, { domain_suffix: e.target.value })} /> },
          { title: "可发布", width: 80, render: (_, r, i) => <Switch checked={r.publishable} onChange={(v) => set(i, { publishable: v })} /> },
          { title: "审核宽严", width: 100, render: (_, r, i) => (
            <Select value={r.review_strictness} style={{ width: 90 }} options={options(STRICTNESS_LABEL)}
              onChange={(v) => set(i, { review_strictness: v })} />) },
          { title: "能否带外链", width: 130, render: (_, r, i) => (
            <Select value={r.allows_links} style={{ width: 120 }} options={options(LINKS_LABEL)}
              onChange={(v) => set(i, { allows_links: v })} />) },
          { title: "发布注意事项", render: (_, r, i) => <Input value={r.notes} maxLength={500} onChange={(e) => set(i, { notes: e.target.value })} /> },
          { title: "", width: 60, render: (_, __, i) => <Button size="small" danger onClick={() => setRows(rows.filter((_, j) => j !== i))}>删</Button> },
        ]} />
      <Space>
        <Button onClick={() => setRows([...rows, { key: "", name: "", domain_suffix: "", publishable: true, review_strictness: "unknown", allows_links: "unknown", notes: "" }])}>新增一行</Button>
        <Button type="primary" onClick={() => send("PUT", "/settings/platforms", rows).then(() => { message.success("已保存并重算"); load(); }).catch(fail)}>保存</Button>
      </Space>
    </Space>
  );
}

function OwnedPrefixes() {
  const [rows, setRows] = useState<{ id: number; name: string; url_prefix: string }[]>([]);
  const [form] = Form.useForm();
  const load = () => get<typeof rows>("/settings/owned-prefixes").then(setRows);
  useEffect(() => { load(); }, []);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">官网、头条号、抖音号等的 URL 前缀。信源 URL 以它开头就算“自有内容”。增删后重算全部信源。</Typography.Text>
      <Table size="small" rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: "名称", dataIndex: "name" },
          { title: "URL 前缀", dataIndex: "url_prefix" },
          { title: "", width: 60, render: (_, r) => (
            <Popconfirm title="删除这个前缀？" onConfirm={() => send("DELETE", `/settings/owned-prefixes/${r.id}`).then(load).catch(fail)}>
              <Button size="small" danger>删</Button>
            </Popconfirm>) },
        ]} />
      <Form form={form} layout="inline" onFinish={(v) => send("POST", "/settings/owned-prefixes", v).then(() => { form.resetFields(); load(); }).catch(fail)}>
        <Form.Item name="name" rules={[{ required: true }]}><Input placeholder="名称，如：澳觅官网" /></Form.Item>
        <Form.Item name="url_prefix" rules={[{ required: true }]}><Input placeholder="如：aomi.mo 或 https://www.toutiao.com/c/user/…" style={{ width: 360 }} /></Form.Item>
        <Button htmlType="submit">添加</Button>
      </Form>
    </Space>
  );
}

function BrandMarks() {
  const [rows, setRows] = useState<(BrandMark & { id: number })[]>([]);
  const [version, setVersion] = useState(0);
  const load = () => get<{ version: number; marks: BrandMark[] }>("/settings/brand-marks").then((r) => {
    setVersion(r.version);
    setRows(r.marks.map((m, i) => ({ ...m, id: i })));
  });
  useEffect(() => { load(); }, []);
  const update = (id: number, patch: Partial<BrandMark>) => setRows(rows.map((r) => (r.id === id ? { ...r, ...patch } : r)));
  const save = () => send<{ version: number }>("PUT", "/settings/brand-marks", rows.map(({ kind, value }) => ({ kind, value })))
    .then((r) => { message.success(`已保存为第 ${r.version} 版`); load(); }).catch(fail);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">
        当前第 {version} 版。看板「品牌归因」按这份清单在回答正文里找官方入口：网址等不区分大小写，电话只比数字。每次保存生成新版本。
      </Typography.Text>
      <Table size="small" pagination={false} rowKey="id" dataSource={rows} columns={[
        { title: "类型", dataIndex: "kind", width: 160, render: (v, r) => (
          <Select value={v} style={{ width: 140 }} onChange={(k) => update(r.id, { kind: k })}
            options={Object.entries(MARK_KIND_LABEL).map(([value, label]) => ({ value, label }))} />) },
        { title: "内容", dataIndex: "value", render: (v, r) => (
          <Input value={v} maxLength={128} onChange={(e) => update(r.id, { value: e.target.value })}
            placeholder={r.kind === "phone" ? "不带区号，例如 2888 8888" : "例如 aomiapp.com"} />) },
        { title: "", width: 70, render: (_, r) => <a onClick={() => setRows(rows.filter((x) => x.id !== r.id))}>删除</a> },
      ]} />
      <Space>
        <Button onClick={() => setRows([...rows, { id: Math.max(-1, ...rows.map((r) => r.id)) + 1, kind: "website", value: "" }])}>添加</Button>
        <Button type="primary" onClick={save}>保存</Button>
      </Space>
    </Space>
  );
}

function Params() {
  const [form] = Form.useForm();
  useEffect(() => { get<Record<string, string>>("/settings").then((s) => form.setFieldsValue(s)); }, [form]);
  const save = (v: Record<string, unknown>) => {
    const body = Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === null || x === undefined ? "" : String(x)]));
    send("PUT", "/settings", body).then(() => message.success("已保存")).catch(fail);
  };
  return (
    <Form form={form} layout="vertical" style={{ maxWidth: 520 }} onFinish={save}>
      <Form.Item name="api_channel" label="API 渠道" extra="换渠道后看板按渠道分开显示，不和之前的数据接成一条线">
        <Select options={[{ value: "api-custom", label: "api-custom（联网搜索 Custom 版）" }, { value: "api-plugin", label: "api-plugin（联网内容插件）" }]} />
      </Form.Item>
      <Form.Item name="repeats_per_question_api" label="每题次数（API，每天每题问几次；改动即改口径）"
        extra="改了以后趋势图在那一天画竖线；改回 1 不删当天已采到的第 2 次">
        <InputNumber min={1} max={5} precision={0} />
      </Form.Item>
      <Form.Item name="weak_recent_n" label="短板题：看最近几次采集"><InputNumber min={1} max={60} /></Form.Item>
      <Form.Item name="weak_mention_ratio" label="短板题：澳觅提及比例低于"><InputNumber min={0.05} max={1} step={0.05} /></Form.Item>
      <Form.Item name="platform_window_days" label="平台推荐与参照文章：统计近几天"><InputNumber min={1} max={366} /></Form.Item>
      <Form.Item name="price_per_search_yuan" label="单价：每次计费搜索（元）"><InputNumber min={0} step={0.001} /></Form.Item>
      <Form.Item name="price_input_per_1k_yuan" label="单价：每千输入 token（元）"><InputNumber min={0} step={0.0001} /></Form.Item>
      <Form.Item name="price_output_per_1k_yuan" label="单价：每千输出 token（元）" extra="三项单价都填了，看板才显示估算费用">
        <InputNumber min={0} step={0.0001} />
      </Form.Item>
      <Button type="primary" htmlType="submit">保存</Button>
    </Form>
  );
}

interface Job { id: number; run_date: string; channel: string; status: string; requested_by: string | null; started_at: string | null; finished_at: string | null; n_ok: number; n_failed: number; message: string }
const JOB_COLOR: Record<string, string> = { done: "green", failed: "red", running: "blue", requested: "gold" };

function Jobs() {
  const [rows, setRows] = useState<Job[]>([]);
  const load = () => get<Job[]>("/settings/jobs", { limit: 30 }).then(setRows);
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  const today = cstToday();
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Space>
        <Popconfirm title={`补跑今天（${today}）？`} description="已成功的题会跳过，只重跑失败和缺失的题。由 worker 排队执行。"
          onConfirm={() => send("POST", "/settings/jobs/rerun", { date: today }).then(() => { message.success("已加入队列"); load(); }).catch(fail)}>
          <Button type="primary">补跑今天</Button>
        </Popconfirm>
        <Typography.Text type="secondary">只能补跑北京时间当天。每天 10:00 自动采集。</Typography.Text>
      </Space>
      <Table<Job> size="small" rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: "日期", dataIndex: "run_date", width: 110 },
          { title: "渠道", dataIndex: "channel", width: 110 },
          { title: "状态", dataIndex: "status", width: 80, render: (s) => <Tag color={JOB_COLOR[s]}>{s}</Tag> },
          { title: "发起", dataIndex: "requested_by", width: 90, render: (v) => v ?? "定时" },
          { title: "开始", dataIndex: "started_at", width: 160, render: (v) => v?.replace("T", " ").slice(0, 19) ?? "—" },
          { title: "成功/失败", width: 90, render: (_, r) => `${r.n_ok}/${r.n_failed}` },
          { title: "说明", dataIndex: "message" },
        ]} />
    </Space>
  );
}

interface U { id: number; username: string; is_active: boolean; created_at: string }

function Users() {
  const [rows, setRows] = useState<U[]>([]);
  const [form] = Form.useForm();
  const load = () => get<U[]>("/settings/users").then(setRows);
  useEffect(() => { load(); }, []);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Table<U> size="small" rowKey="id" dataSource={rows} pagination={false}
        columns={[
          { title: "用户名", dataIndex: "username" },
          { title: "创建时间", dataIndex: "created_at", render: (v) => v.replace("T", " ").slice(0, 19) },
          { title: "启用", dataIndex: "is_active", width: 80, render: (v, u) => (
            <Switch checked={v} onChange={(on) => send("PATCH", `/settings/users/${u.id}`, { is_active: on }).then(load).catch(fail)} />) },
        ]} />
      <Form form={form} layout="inline" onFinish={(v) => send("POST", "/settings/users", v).then(() => { form.resetFields(); load(); message.success("已创建"); }).catch(fail)}>
        <Form.Item name="username" rules={[{ required: true, whitespace: true, max: 64 }]}><Input placeholder="用户名" /></Form.Item>
        <Form.Item name="password" rules={[{ required: true, min: 8, max: 72 }]}><Input.Password placeholder="初始密码（≥8 位）" /></Form.Item>
        <Button htmlType="submit">新建账号</Button>
      </Form>
    </Space>
  );
}

function FactItems() {
  const [rows, setRows] = useState<(FactItem & { _key: number })[]>([]);
  const [version, setVersion] = useState(0);
  const load = () => get<{ version: number; items: FactItem[] }>("/settings/fact-items").then((r) => {
    setVersion(r.version);
    setRows(r.items.map((m, i) => ({ ...m, _key: i })));
  });
  useEffect(() => { load(); }, []);
  const update = (key: number, patch: Partial<FactItem>) => setRows(rows.map((r) => (r._key === key ? { ...r, ...patch } : r)));
  const save = () => send<{ version: number }>("PUT", "/settings/fact-items", rows.map(({ code, category, subject, correct_claim, source_ref, status }) => ({ code, category, subject, correct_claim, source_ref, status })))
    .then((r) => { message.success(`已保存为第 ${r.version} 版`); load(); }).catch(fail);
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">
        当前第 {version} 版。清单用于事实一致性检测。每次保存生成新版本，已抽取的结果不会自动重判。
      </Typography.Text>
      <Table size="small" pagination={false} rowKey="_key" dataSource={rows} scroll={{ x: 900 }} columns={[
        { title: "编号", dataIndex: "code", width: 80, render: (v, r) => (
          <Input value={v} maxLength={16} onChange={(e) => update(r._key, { code: e.target.value })} placeholder="A1" />) },
        { title: "分类", dataIndex: "category", width: 120, render: (v, r) => (
          <Select value={v} style={{ width: 110 }} onChange={(c) => update(r._key, { category: c })}
            options={Object.entries(FACT_CATEGORY_LABEL).map(([value, label]) => ({ value, label }))} />) },
        { title: "主题", dataIndex: "subject", width: 160, render: (v, r) => (
          <Input value={v} maxLength={64} onChange={(e) => update(r._key, { subject: e.target.value })} />) },
        { title: "正确说法", dataIndex: "correct_claim", render: (v, r) => (
          <Input.TextArea value={v} autoSize={{ minRows: 1, maxRows: 4 }} onChange={(e) => update(r._key, { correct_claim: e.target.value })} />) },
        { title: "出处", dataIndex: "source_ref", width: 140, render: (v, r) => (
          <Input value={v} maxLength={128} onChange={(e) => update(r._key, { source_ref: e.target.value })} />) },
        { title: "状态", dataIndex: "status", width: 100, render: (v, r) => (
          <Select value={v} style={{ width: 90 }} onChange={(s) => update(r._key, { status: s })}
            options={[{ value: "active", label: "启用" }, { value: "retired", label: "停用" }]} />) },
        { title: "", width: 60, render: (_, r) => <a onClick={() => setRows(rows.filter((x) => x._key !== r._key))}>删除</a> },
      ]} />
      <Space>
        <Button onClick={() => setRows([...rows, { _key: Math.max(-1, ...rows.map((r) => r._key)) + 1, code: "", category: "other", subject: "", correct_claim: "", source_ref: "", status: "active" }])}>添加</Button>
        <Button type="primary" onClick={save}>保存</Button>
      </Space>
    </Space>
  );
}

export default function Settings() {
  const [params] = useSearchParams();
  return (
    <Card className="ab-card" size="small">
      <Tabs defaultActiveKey={params.get("tab") ?? undefined} items={[
        { key: "aliases", label: "竞品别名表", children: <Aliases /> },
        { key: "platforms", label: "平台映射", children: <Platforms /> },
        { key: "owned", label: "自有渠道", children: <OwnedPrefixes /> },
        { key: "marks", label: "官方标识", children: <BrandMarks /> },
        { key: "facts", label: "事实清单", children: <FactItems /> },
        { key: "params", label: "阈值与单价", children: <Params /> },
        { key: "jobs", label: "采集任务", children: <Jobs /> },
        { key: "users", label: "账号", children: <Users /> },
      ]} />
    </Card>
  );
}
