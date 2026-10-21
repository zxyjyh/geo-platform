export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

/** 所有请求都带 cookie；401 时跳到登录页（登录接口自己的 401 交给调用方处理）。 */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await fetch(`/api${path}`, {
    credentials: "include",
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers || {}) },
  });
  if (r.status === 401 && path !== "/auth/login") {
    if (window.location.pathname !== "/login") window.location.assign("/login");
    throw new ApiError(401, "未登录");
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const j = await r.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* 非 JSON 响应，保留 statusText */
    }
    throw new ApiError(r.status, detail);
  }
  return r.json() as Promise<T>;
}

export const get = <T,>(path: string, params?: Record<string, string | number | boolean | undefined | null>) => {
  const qs = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  });
  const q = qs.toString();
  return api<T>(q ? `${path}?${q}` : path);
};

export const send = <T,>(method: "POST" | "PUT" | "PATCH" | "DELETE", path: string, body?: unknown) =>
  api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
