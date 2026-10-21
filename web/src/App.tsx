import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Button, Layout, Menu, Result, Spin, Typography } from "antd";
import {
  BarChartOutlined, BulbOutlined, DashboardOutlined, LinkOutlined, LogoutOutlined, QuestionCircleOutlined,
  SettingOutlined, UnorderedListOutlined,
} from "@ant-design/icons";
import { api, send } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";

const NAV = [
  { key: "/", icon: <DashboardOutlined />, label: "看板" },
  { key: "/runs", icon: <UnorderedListOutlined />, label: "回答记录" },
  { key: "/questions", icon: <QuestionCircleOutlined />, label: "题目" },
  { key: "/sources", icon: <LinkOutlined />, label: "信源分析" },
  { key: "/suggestions", icon: <BulbOutlined />, label: "优化建议" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置" },
];

function Shell() {
  const [user, setUser] = useState<string | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  useEffect(() => {
    api<{ username: string }>("/auth/me").then((u) => setUser(u.username)).catch(() => undefined);
  }, []);
  if (!user) return <Spin style={{ display: "block", marginTop: 120 }} />;
  const selected = NAV.find((n) => n.key !== "/" && loc.pathname.startsWith(n.key))?.key ?? "/";
  return (
    <Layout style={{ minHeight: "100%" }}>
      <Layout.Sider width={200} theme="dark">
        <div style={{ color: "#fff", padding: "18px 20px", fontWeight: 600, fontSize: 16 }}>
          <BarChartOutlined /> 豆包 GEO
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={NAV} onClick={(e) => nav(e.key)} />
      </Layout.Sider>
      <Layout>
        <Layout.Header style={{ background: "#fff", padding: "0 24px", display: "flex", justifyContent: "flex-end",
          alignItems: "center", gap: 12, borderBottom: "1px solid #eee" }}>
          <Typography.Text type="secondary">{user}</Typography.Text>
          <Button size="small" icon={<LogoutOutlined />}
            onClick={() => send("POST", "/auth/logout").finally(() => window.location.assign("/login"))}>
            退出
          </Button>
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

const Todo = () => <Result status="info" title="页面开发中" />;

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Shell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs" element={<Todo />} />
          <Route path="/questions" element={<Todo />} />
          <Route path="/sources" element={<Todo />} />
          <Route path="/suggestions" element={<Todo />} />
          <Route path="/settings" element={<Todo />} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
