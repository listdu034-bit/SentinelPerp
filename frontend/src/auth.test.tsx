// @vitest-environment jsdom
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import MockAdapter from "axios-mock-adapter";
import { AuthProvider, authHttp } from "./auth";
import { getToken, setToken } from "./session";
import { http } from "./api";
import { m2Http } from "./m2";
import App from "./App";

vi.mock("./pages/Status", () => ({ default: () => <h1>Protected status</h1> }));
vi.mock("./pages/Opportunities", () => ({
  default: () => <h1>Protected opportunities</h1>,
}));
beforeAll(() => {
  window.matchMedia = vi
    .fn()
    .mockImplementation(() => ({
      matches: false,
      addListener() {},
      removeListener() {},
      addEventListener() {},
      removeEventListener() {},
    }));
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  const original = window.getComputedStyle;
  window.getComputedStyle = (element) => original(element);
});
afterEach(() => {
  cleanup();
  sessionStorage.clear();
});
const operator = {
  username: "operator",
  expires_at: Math.floor(Date.now() / 1000) + 3600,
};
function setup(path = "/opportunities") {
  const mock = new MockAdapter(authHttp);
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter
        initialEntries={[path]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return {
    mock,
    client,
    close: () => {
      view.unmount();
      client.clear();
      mock.restore();
    },
  };
}
async function fillLogin() {
  fireEvent.change(await screen.findByLabelText("用户名"), {
    target: { value: "operator" },
  });
  fireEvent.change(screen.getByLabelText("密码"), {
    target: { value: "password" },
  });
  fireEvent.click(screen.getByRole("button", { name: /登录工作台/ }));
}
it("redirects anonymous routes, shows wrong credentials, then returns to requested page", async () => {
  const { mock, close } = setup();
  try {
    expect(await screen.findByText("登录您的市场分析工作台")).toBeTruthy();
    expect(screen.queryByText("Protected opportunities")).toBeNull();
    mock
      .onPost("/auth/jwt/login")
      .replyOnce(401, { error: { message: "用户名或密码错误" } });
    await fillLogin();
    expect(await screen.findByText("用户名或密码错误")).toBeTruthy();
    expect(getToken()).toBeNull();
    mock.onPost("/auth/jwt/login").reply(200, { access_token: "new-token" });
    mock.onGet("/users/me").reply(200, operator);
    fireEvent.click(screen.getByRole("button", { name: /登录工作台/ }));
    expect(
      await screen.findByText(
        "Protected opportunities",
        {},
        { timeout: 10000 },
      ),
    ).toBeTruthy();
    expect(getToken()).toBe("new-token");
    expect(mock.history.get[0].headers?.Authorization).toBe("Bearer new-token");
  } finally {
    close();
  }
}, 20000);
it("restores a verified session and revokes it on logout, clearing cached data", async () => {
  setToken("saved-token");
  const { mock: inner, client, close } = setup("/status");
  inner.onGet("/users/me").reply(200, operator);
  inner.onPost("/auth/jwt/logout").reply(204);
  try {
    expect(
      await screen.findByText("Protected status", {}, { timeout: 10000 }),
    ).toBeTruthy();
    client.setQueryData(["private"], "secret");
    fireEvent.click(screen.getByRole("button", { name: /退出登录/ }));
    expect(await screen.findByText("登录您的市场分析工作台")).toBeTruthy();
    expect(getToken()).toBeNull();
    expect(client.getQueryData(["private"])).toBeUndefined();
  } finally {
    close();
  }
}, 20000);
it("rejects a stored invalid token before rendering protected content", async () => {
  setToken("expired-token");
  const { mock, close } = setup("/status");
  mock.onGet("/users/me").reply(401);
  try {
    expect(await screen.findByText("登录您的市场分析工作台")).toBeTruthy();
    expect(screen.queryByText("Protected status")).toBeNull();
    expect(getToken()).toBeNull();
  } finally {
    close();
  }
});
it("attaches bearer tokens to both business API clients and clears the session on 401", async () => {
  setToken("current-token");
  const first = new MockAdapter(http),
    second = new MockAdapter(m2Http);
  first.onGet("/status").reply(200, {});
  second.onPost("/analysis/create").reply(200, {});
  try {
    await http.get("/status");
    await m2Http.post("/analysis/create", {});
    expect(first.history.get[0].headers?.Authorization).toBe(
      "Bearer current-token",
    );
    expect(second.history.post[0].headers?.Authorization).toBe(
      "Bearer current-token",
    );
    second.onGet("/analysis").reply(401);
    await expect(m2Http.get("/analysis")).rejects.toBeTruthy();
    await waitFor(() => expect(getToken()).toBeNull());
  } finally {
    first.restore();
    second.restore();
  }
});
