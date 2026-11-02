import { Suspense, lazy, useState } from "react";
import { Alert, Button, Layout, Menu, Result, Spin, Typography } from "antd";
import {
  DashboardOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
} from "@ant-design/icons";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { errorMessage } from "./api";
import Login from "./pages/Login";
const FeatureAnalysis = lazy(() => import("./pages/FeatureAnalysis"));
const Opportunities = lazy(() => import("./pages/Opportunities"));
const Status = lazy(() => import("./pages/Status"));
const Rankings = lazy(() => import("./pages/Rankings"));
const Market = lazy(() => import("./pages/Market"));
const Quality = lazy(() => import("./pages/Quality"));
const items = [
  ["/status", "系统状态", <DashboardOutlined />],
  ["/rankings", "涨跌幅榜单", <FundOutlined />],
  ["/markets/BTC-USDT-SWAP", "市场详情", <LineChartOutlined />],
  ["/feature-analysis", "特征分析", <LineChartOutlined />],
  ["/opportunities", "机会发现", <FundOutlined />],
  ["/quality", "数据质量", <SafetyCertificateOutlined />],
] as const;
export default function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}
function AuthenticatedApp() {
  const { user, loading, logout } = useAuth();
  const location = useLocation();
  const { pathname } = location;
  const [logoutError, setLogoutError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  if (loading) return <Spin size="large" />;
  if (pathname === "/login") return <Login />;
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: pathname + location.search + location.hash }}
      />
    );
  }
  const active = pathname.startsWith("/markets")
    ? "/markets/BTC-USDT-SWAP"
    : pathname;
  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Layout.Sider breakpoint="lg" collapsedWidth={0} width={232}>
        <div className="brand">
          <SafetyCertificateOutlined /> SentinelPerp
          <Typography.Text
            style={{ color: "#9eb0c9", display: "block", fontSize: 12 }}
          >
            永续合约数据控制台
          </Typography.Text>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[active]}
          items={items.map(([key, label, icon]) => ({
            key,
            icon,
            label: <Link to={key}>{label}</Link>,
          }))}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="header">
          <Typography.Text strong>市场数据监控</Typography.Text>
          <Typography.Text type="secondary">
            OKX / USDT PERPETUAL
          </Typography.Text>
          <Typography.Text>{user.username}</Typography.Text>
          <Button
            loading={loggingOut}
            onClick={async () => {
              setLogoutError("");
              setLoggingOut(true);
              try {
                await logout();
              } catch (cause) {
                setLogoutError(errorMessage(cause));
              } finally {
                setLoggingOut(false);
              }
            }}
          >
            退出登录
          </Button>
        </Layout.Header>
        <Layout.Content className="content">
          {logoutError && <Alert type="error" showIcon message={logoutError} />}
          <Suspense fallback={<Spin size="large" />}>
            <Routes>
              <Route path="/" element={<Navigate to="/status" replace />} />
              <Route path="/status" element={<Status />} />
              <Route path="/rankings" element={<Rankings />} />
              <Route
                path="/markets"
                element={<Navigate to="/markets/BTC-USDT-SWAP" replace />}
              />
              <Route path="/markets/:symbol" element={<Market />} />
              <Route path="/feature-analysis" element={<FeatureAnalysis />} />
              <Route path="/opportunities" element={<Opportunities />} />
              <Route path="/quality" element={<Quality />} />
              <Route
                path="*"
                element={
                  <Result
                    status="404"
                    title="页面不存在"
                    extra={<Link to="/status">返回系统状态</Link>}
                  />
                }
              />
            </Routes>
          </Suspense>
        </Layout.Content>
        <Layout.Footer style={{ textAlign: "center" }}>
          SentinelPerp · 市场特征分析控制台
        </Layout.Footer>
      </Layout>
    </Layout>
  );
}
