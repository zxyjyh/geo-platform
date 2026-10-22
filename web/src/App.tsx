import { useCallback, useEffect, useState } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Avatar, Button, Layout, Menu, Result, Space, Spin, Typography } from "antd";
import {
  AppstoreOutlined, BulbOutlined, FileSearchOutlined, LinkOutlined, LogoutOutlined, QuestionCircleOutlined,
  SettingOutlined,
} from "@ant-design/icons";
import { api, ApiError, send } from "./api";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Runs from "./pages/Runs";
import Questions from "./pages/Questions";
import Sources from "./pages/Sources";
import Suggestions from "./pages/Suggestions";
import Settings from "./pages/Settings";

// 菜单分组参考 Answerbit：品牌 / 数据 / 优化 / 工作空间
const PAGES = [
  { key: "/", icon: <AppstoreOutlined />, label: "概览", group: "品牌" },
  { key: "/questions", icon: <QuestionCircleOutlined />, label: "用户提问", group: "品牌" },
  { key: "/sources", icon: <LinkOutlined />, label: "信源分析", group: "数据" },
  { key: "/runs", icon: <FileSearchOutlined />, label: "大模型回答记录", group: "数据" },
  { key: "/suggestions", icon: <BulbOutlined />, label: "优化建议", group: "优化" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置", group: "工作空间" },
];
const MENU = ["品牌", "数据", "优化", "工作空间"].map((g) => ({
  type: "group" as const, label: g,
  children: PAGES.filter((p) => p.group === g).map(({ key, icon, label }) => ({ key, icon, label })),
}));

function Shell() {
  const [user, setUser] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();
  const loc = useLocation();
  const load = useCallback(() => {
    setError(null);
    api<{ username: string }>("/auth/me").then((u) => setUser(u.username)).catch((e) => {
      // 401 已由 api.ts 跳转登录页；其他错误（服务挂了、网络断了）要让人看到并能重试
      if (!(e instanceof ApiError && e.status === 401)) setError(String(e.message || e));
    });
  }, []);
  useEffect(load, [load]);
  if (error) {
    return <Result status="error" title="连不上服务器" subTitle={error}
      extra={<Button type="primary" onClick={load}>重试</Button>} />;
  }
  if (!user) return <Spin style={{ display: "block", marginTop: 120 }} />;
  const page = PAGES.find((p) => p.key !== "/" && loc.pathname.startsWith(p.key)) ?? PAGES[0];
  return (
    <Layout style={{ minHeight: "100%" }}>
      <Layout.Sider width={220} style={{ borderRight: "1px solid #eef0f4" }}>
        <div style={{ padding: "18px 20px 10px", fontWeight: 700, fontSize: 18, color: "#1f2937" }}>
          <span style={{ color: "#5B5CF6" }}>◆</span> 澳觅GEO
        </div>
        <Space style={{ padding: "4px 20px 12px" }}>
          <Avatar size={32} style={{ background: "#EEF0FF", color: "#5B5CF6", fontSize: 12 }}>澳觅</Avatar>
          <div>
            <div style={{ fontWeight: 600 }}>澳觅</div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>竞品：mFood、闪蜂</Typography.Text>
          </div>
        </Space>
        <Menu mode="inline" selectedKeys={[page.key]} items={MENU} onClick={(e) => nav(e.key)}
          style={{ borderInlineEnd: "none" }} />
      </Layout.Sider>
      <Layout>
        <Layout.Header style={{ padding: "0 24px", display: "flex", justifyContent: "space-between",
          alignItems: "center", borderBottom: "1px solid #eef0f4", height: 56 }}>
          <Space style={{ fontWeight: 600, fontSize: 16 }}>{page.icon}{page.label}</Space>
          <Space>
            <Typography.Text type="secondary">{user}</Typography.Text>
            <Button size="small" icon={<LogoutOutlined />}
              onClick={() => send("POST", "/auth/logout").finally(() => window.location.assign("/login"))}>
              退出
            </Button>
          </Space>
        </Layout.Header>
        <Layout.Content style={{ padding: 24 }}>
          <Outlet />
        </Layout.Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Shell />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/questions" element={<Questions />} />
          <Route path="/sources" element={<Sources />} />
          <Route path="/runs" element={<Runs />} />
          <Route path="/suggestions" element={<Suggestions />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
