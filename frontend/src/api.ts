const TOKEN_KEY = "jf_token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lasts until reload */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

// In-flight request count, so the UI can show a top progress bar.
let inFlight = 0;
const listeners = new Set<(n: number) => void>();
export function onActivity(fn: (n: number) => void) {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}
function track(delta: number) {
  inFlight = Math.max(0, inFlight + delta);
  listeners.forEach((fn) => fn(inFlight));
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  track(1);
  try {
    return await send<T>(method, path, body, query);
  } finally {
    track(-1);
  }
}

async function send<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const url = new URL("/api" + path, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof URLSearchParams) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(url, { method, headers, body: payload });
  if (res.status === 401 && path !== "/auth/login") {
    setToken(null);
    window.location.assign("/login");
  }
  const data = res.headers.get("content-type")?.includes("json") ? await res.json() : null;
  if (!res.ok) {
    const detail = data?.detail;
    const msg = Array.isArray(detail) ? detail.map((d: { msg: string }) => d.msg).join("; ") : detail;
    throw new ApiError(res.status, msg || res.statusText);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  login: (username: string, password: string) =>
    request<{ access_token: string; user: import("./types").User }>(
      "POST", "/auth/login", new URLSearchParams({ username, password })),
};
