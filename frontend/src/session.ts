import type { AxiosInstance } from "axios";

const KEY = "sentinelperp.access-token";
const EVENT = "sentinelperp:session";
export const getToken = () => sessionStorage.getItem(KEY);
export function setToken(token: string | null) {
  if (token) sessionStorage.setItem(KEY, token);
  else sessionStorage.removeItem(KEY);
  window.dispatchEvent(new Event(EVENT));
}
export function subscribeSession(listener: () => void) {
  window.addEventListener(EVENT, listener);
  return () => window.removeEventListener(EVENT, listener);
}
export function authenticated(client: AxiosInstance) {
  client.interceptors.request.use((config) => {
    const token = getToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
    return config;
  });
  client.interceptors.response.use(undefined, (error) => {
    // A late response from a previous session must not sign out a new login.
    const token = getToken();
    if (
      error.response?.status === 401 &&
      token &&
      error.config?.headers?.Authorization === `Bearer ${token}`
    )
      setToken(null);
    return Promise.reject(error);
  });
  return client;
}
