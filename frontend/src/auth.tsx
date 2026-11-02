import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
  type PropsWithChildren,
} from "react";
import axios from "axios";
import { useQueryClient } from "@tanstack/react-query";
import { authenticated, getToken, setToken, subscribeSession } from "./session";

// Root endpoints share the API host, including when the console uses an absolute URL.
const api = new URL(
  import.meta.env.VITE_API_BASE_URL || "/",
  window.location.origin,
);
export const authHttp = authenticated(
  axios.create({ baseURL: api.origin, timeout: 15000 }),
);
interface User {
  username: string;
  expires_at: number;
}
interface Auth {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}
const Context = createContext<Auth | null>(null);
export function AuthProvider({ children }: PropsWithChildren) {
  const client = useQueryClient();
  const token = useSyncExternalStore(subscribeSession, getToken);
  const [session, setSession] = useState<{ token: string; user: User } | null>(
    null,
  );
  const [failedToken, setFailedToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(!!token);
  const user = session?.token === token ? session.user : null;
  useEffect(() => {
    let active = true;
    setSession(null);
    setFailedToken(null);
    void client.cancelQueries();
    client.clear();
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    authHttp
      .get<User>("/users/me")
      .then(({ data }) => {
        if (active) setSession({ token, user: data });
      })
      .catch(() => {
        if (active && getToken() === token) setToken(null);
      })
      .finally(() => {
        if (active) {
          setFailedToken(token);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [token, client]);
  useEffect(() => {
    if (!user) return;
    const timer = window.setTimeout(
      () => setToken(null),
      Math.max(0, user.expires_at * 1000 - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [user]);
  return (
    <Context.Provider
      value={{
        user,
        loading: loading || (!!token && !user && failedToken !== token),
        login: async (username, password) => {
          const { data } = await authHttp.post<{ access_token: string }>(
            "/auth/jwt/login",
            new URLSearchParams({ username, password }),
          );
          setToken(data.access_token);
        },
        logout: async () => {
          // Remain on the current page if revocation fails, so the user can retry.
          await authHttp.post("/auth/jwt/logout");
          setToken(null);
        },
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const auth = useContext(Context);
  if (!auth) throw new Error("AuthProvider is required");
  return auth;
}
