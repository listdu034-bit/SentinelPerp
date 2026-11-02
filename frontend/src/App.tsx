import { Suspense, lazy } from "react";
import { Alert, Button, Result, Spin } from "antd";
import { ProLayout } from "@ant-design/pro-components";
import { useState } from "react";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import {
  DashboardOutlined,
  FundOutlined,
  LineChartOutlined,
  SafetyCertificateOutlined,
  LogoutOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
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
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return (
      <div className="session-loading">
        <Spin size="large" tip="正在验证登录状态" fullscreen />
      </div>
    );
  if (location.pathname === "/login") return <Login />;
  if (!user)
    return (
      <Navigate
        to="/login"
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  return <Workspace />;
}
function Workspace() {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  return (
    <ProLayout
      title="SentinelPerp"
      logo={<SafetyCertificateOutlined />}
      layout="mix"
      navTheme="realDark"
      fixSiderbar
      fixedHeader
      location={{ pathname }}
      route={{
        routes: items.map(([path, name, icon]) => ({ path, name, icon })),
      }}
      menuItemRender={(item, dom) => (
        <Link to={item.path || "/status"}>{dom}</Link>
      )}
      avatarProps={{ icon: <UserOutlined />, title: user?.username }}
      actionsRender={() => [
        <Button
          key="logout"
          type="text"
          icon={<LogoutOutlined />}
          loading={leaving}
          onClick={async () => {
            setLeaving(true);
            setError("");
            try {
              await logout();
            } catch {
              setError("退出失败，请检查网络后重试");
            } finally {
              setLeaving(false);
            }
          }}
        >
          退出登录
        </Button>,
      ]}
      token={{
        header: {
          colorBgHeader: "#101c30",
          colorTextMenu: "#c3d0e5",
          colorTextMenuSelected: "#76b7ff",
          colorTextMenuActive: "#76b7ff",
        },
        sider: {
          colorMenuBackground: "#0e1829",
          colorTextMenu: "#a8b9d2",
          colorTextMenuSelected: "#76b7ff",
        },
      }}
      footerRender={() => (
        <div className="workspace-footer">
          SentinelPerp · 市场特征分析控制台
        </div>
      )}
    >
      {error && (
        <Alert
          type="error"
          message={error}
          closable
          onClose={() => setError("")}
        />
      )}
      <div className="workspace-label">
        OKX / USDT PERPETUAL <span>市场数据与智能分析</span>
      </div>
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
    </ProLayout>
  );
}
