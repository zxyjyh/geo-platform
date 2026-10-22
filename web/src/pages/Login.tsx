import { useState } from "react";
import { Alert, Button, Card, Form, Input, Typography } from "antd";
import { ApiError, send } from "../api";

export default function Login() {
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const onFinish = async (v: { username: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      await send("POST", "/auth/login", v);
      window.location.assign("/");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };
  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%" }}>
      <Card style={{ width: 360 }}>
        <Typography.Title level={4} style={{ marginTop: 0 }}>澳觅GEO · 内部</Typography.Title>
        {error && <Alert type="error" message={error} showIcon style={{ marginBottom: 16 }} />}
        <Form layout="vertical" onFinish={onFinish}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}>
            <Input autoComplete="username" autoFocus />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true }]}>
            <Input.Password autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={loading}>登录</Button>
        </Form>
      </Card>
    </div>
  );
}
