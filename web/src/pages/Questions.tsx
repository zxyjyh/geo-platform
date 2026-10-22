import { useEffect, useState } from "react";
import { Button, Card, Form, Input, Modal, Select, Space, Table, Tag, message } from "antd";
import { PlusOutlined, EditOutlined, DeleteOutlined } from "@ant-design/icons";
import { get, send } from "../api";

interface Q { qid: string; version: string; text: string; branded: boolean; scene: string; intent: string; status: string }

export default function Questions() {
  const [qs, setQs] = useState<Q[] | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingQ, setEditingQ] = useState<Q | null>(null);
  const [form] = Form.useForm();

  const load = () => { get<Q[]>("/questions").then(setQs); };
  useEffect(load, []);

  const handleAdd = () => {
    setEditingQ(null);
    form.resetFields();
    setModalOpen(true);
  };

  const handleEdit = (q: Q) => {
    setEditingQ(q);
    form.setFieldsValue(q);
    setModalOpen(true);
  };

  const handleDelete = async (qid: string) => {
    if (!confirm(`确定删除题目 ${qid}？`)) return;
    try {
      await send("DELETE", `/questions/${qid}`);
      message.success("删除成功");
      load();
    } catch (e) {
      message.error("删除失败");
    }
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingQ) {
        await send("PUT", `/questions/${editingQ.qid}`, values);
        message.success("更新成功");
      } else {
        await send("POST", "/questions", values);
        message.success("添加成功");
      }
      setModalOpen(false);
      load();
    } catch (e) {
      message.error("操作失败");
    }
  };

  return (
    <Card className="ab-card" size="small" title="用户提问"
      extra={<Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>添加题目</Button>}>
      <Table<Q> size="middle" rowKey="qid" loading={!qs} dataSource={qs ?? []} pagination={false}
        columns={[
          { title: "编号", dataIndex: "qid", width: 70 },
          { title: "题目", dataIndex: "text" },
          { title: "带品牌名", dataIndex: "branded", width: 160,
            render: (b) => (b ? <Tag color="orange">是 · 不计入提及率</Tag> : <Tag color="purple">否</Tag>) },
          { title: "场景", dataIndex: "scene", width: 180 },
          { title: "意图", dataIndex: "intent", width: 80 },
          { title: "版本", dataIndex: "version", width: 70, render: (v, q) => <span>{v} <Tag>{q.status}</Tag></span> },
          { title: "操作", width: 120, render: (_, q) => (
            <Space>
              <Button type="link" size="small" icon={<EditOutlined />} onClick={() => handleEdit(q)}>编辑</Button>
              <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => handleDelete(q.qid)}>删除</Button>
            </Space>
          )},
        ]} />
      <Modal title={editingQ ? "编辑题目" : "添加题目"} open={modalOpen} onOk={handleSubmit} onCancel={() => setModalOpen(false)}>
        <Form form={form} layout="vertical">
          {!editingQ && (
            <Form.Item name="qid" label="编号" rules={[{ required: true, message: "请输入编号" }]}>
              <Input placeholder="例如：Q16" />
            </Form.Item>
          )}
          <Form.Item name="text" label="题目" rules={[{ required: true, message: "请输入题目" }]}>
            <Input.TextArea rows={3} placeholder="请输入题目内容" />
          </Form.Item>
          <Form.Item name="branded" label="带品牌名" rules={[{ required: true, message: "请选择" }]}>
            <Select options={[{ value: false, label: "否" }, { value: true, label: "是 · 不计入提及率" }]} />
          </Form.Item>
          <Form.Item name="scene" label="场景">
            <Input placeholder="例如：外卖" />
          </Form.Item>
          <Form.Item name="intent" label="意图">
            <Input placeholder="例如：推荐" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={[{ value: "", label: "草稿" }, { value: "active", label: "启用" }, { value: "archived", label: "归档" }]} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
