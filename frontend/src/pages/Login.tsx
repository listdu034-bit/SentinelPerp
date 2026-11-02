import { useState } from "react";
import { Alert, Typography } from "antd";
import {
  LockOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { LoginForm, ProFormText } from "@ant-design/pro-components";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth";
import { errorMessage } from "../api";

export default function Login() {
  const { user, login } = useAuth();
  const location = useLocation();
  const [error, setError] = useState("");
  const from = location.state?.from;
  const target =
    typeof from === "string" &&
    from.startsWith("/") &&
    !from.startsWith("//") &&
    !from.includes("\\") &&
    !from.startsWith("/login")
      ? from
      : "/status";
  if (user) return <Navigate to={target} replace />;
  return (
    <main className="login-page">
      <section className="login-intro">
        <div className="login-eyebrow">SENTINELPERP / WORKSPACE</div>
        <Typography.Title>
          洞察市场脉动
          <br />
          <span>把握每一次机会</span>
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          永续合约数据、市场特征分析与机会发现，尽在一个专业工作台。
        </Typography.Paragraph>
        <div className="login-features">
          <span>实时市场监控</span>
          <span>智能特征分析</span>
          <span>历史案例检索</span>
        </div>
      </section>
      <section className="login-card">
        <LoginForm<{ username: string; password: string }>
          logo={
            <SafetyCertificateOutlined
              style={{ color: "#5eaaff", fontSize: 36 }}
            />
          }
          title="SentinelPerp"
          subTitle="登录您的市场分析工作台"
          submitter={{ searchConfig: { submitText: "登录工作台" } }}
          onFinish={async ({ username, password }) => {
            setError("");
            try {
              await login(username, password);
              return true;
            } catch (cause) {
              setError(errorMessage(cause));
              return false;
            }
          }}
        >
          {error && (
            <Alert
              type="error"
              showIcon
              message={error}
              style={{ marginBottom: 24 }}
            />
          )}
          <ProFormText
            name="username"
            label="用户名"
            fieldProps={{
              size: "large",
              prefix: <UserOutlined />,
              autoComplete: "username",
            }}
            placeholder="请输入用户名"
            rules={[{ required: true, message: "请输入用户名" }]}
          />
          <ProFormText.Password
            name="password"
            label="密码"
            fieldProps={{
              size: "large",
              prefix: <LockOutlined />,
              autoComplete: "current-password",
            }}
            placeholder="请输入密码"
            rules={[{ required: true, message: "请输入密码" }]}
          />
        </LoginForm>
        <div className="login-footnote">
          <LockOutlined /> 安全访问 · 仅限授权用户
        </div>
      </section>
      <footer className="login-footer">
        SentinelPerp · 永续合约市场分析平台
      </footer>
    </main>
  );
}
