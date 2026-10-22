import { useEffect, useState } from "react";
import {
  Alert, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Switch, Table, Tabs, Tag, Typography, message,
} from "antd";
import { get, send } from "../api";
import { cstToday } from "../format";
import { ENTITIES, ENTITY_NAME, type Entity } from "../types";

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

interface Platform { key: string; name: string; domain_suffix: string; publishable: boolean }

function Platforms() {
  const [rows, setRows] = useState<Platform[]>([]);
  const load = () => get<Platform[]>("/settings/platforms").then(setRows);
  useEffect(() => { load(); }, []);
  const set = (i: number, patch: Partial<Platform>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <Space direction="vertical" style={{ width: "100%" }}>
      <Typography.Text type="secondary">域名等于后缀、或以“.后缀”结尾就算这个平台；多个都能匹配时取最长的后缀。保存后重算全部信源。</Typography.Text>
      <Table<Platform> size="small" rowKey={(_, i) => String(i)} dataSource={rows} pagination={false}
        columns={[
          { title: "key", render: (_, r, i) => <Input value={r.key} onChange={(e) => set(i, { key: e.target.value })} /> },
          { title: "名称", render: (_, r, i) => <Input value={r.name} onChange={(e) => set(i, { name: e.target.value })} /> },
          { title: "域名后缀", render: (_, r, i) => <Input value={r.domain_suffix} onChange={(e) => set(i, { domain_suffix: e.target.value })} /> },
          { title: "可发布", width: 80, render: (_, r, i) => <Switch checked={r.publishable} onChange={(v) => set(i, { publishable: v })} /> },
          { title: "", width: 60, render: (_, __, i) => <Button size="small" danger onClick={() => setRows(rows.filter((_, j) => j !== i))}>删</Button> },
        ]} />
      <Space>
        <Button onClick={() => setRows([...rows, { key: "", name: "", domain_suffix: "", publishable: true }])}>新增一行</Button>
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
        <Typography.Text type="secondary">只能补跑北京时间当天：补跑往日会把今天采到的回答记到那一天。每天 06:00 自动采集。</Typography.Text>
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

export default function Settings() {
  return (
    <Card className="ab-card" size="small">
      <Alert type="info" showIcon style={{ marginBottom: 12 }} message="ARK_API_KEY 等密钥只在服务器的环境变量里，页面上不显示也不能修改。" />
      <Tabs items={[
        { key: "aliases", label: "竞品别名表", children: <Aliases /> },
        { key: "platforms", label: "平台映射", children: <Platforms /> },
        { key: "owned", label: "自有渠道", children: <OwnedPrefixes /> },
        { key: "params", label: "阈值与单价", children: <Params /> },
        { key: "jobs", label: "采集任务", children: <Jobs /> },
        { key: "users", label: "账号", children: <Users /> },
      ]} />
    </Card>
  );
}
