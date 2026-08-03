const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

/** Xoá phiên và đưa về màn đăng nhập — dùng khi refresh token cũng hết hạn. */
function clearSession() {
  ["access_token", "refresh_token", "role", "username"].forEach((k) => localStorage.removeItem(k));
  if (window.location.pathname !== "/login") window.location.assign("/login");
}

// Nhiều request song song cùng gặp 401 chỉ được gọi /auth/refresh một lần;
// các request còn lại chờ chung promise này rồi thử lại.
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;

  const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  }).catch(() => null);

  if (!response?.ok) return false;

  const data = (await response.json()) as { access_token: string; refresh_token: string };
  localStorage.setItem("access_token", data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return true;
}

function buildRequest(path: string, options: RequestInit): Request {
  const headers = new Headers(options.headers);
  // Let the browser set the multipart boundary itself when the body is FormData,
  // and keep the caller's Content-Type for URLSearchParams (form-urlencoded).
  const bodyHasOwnContentType = options.body instanceof FormData || options.body instanceof URLSearchParams;
  if (!bodyHasOwnContentType) headers.set("Content-Type", "application/json");

  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  return new Request(`${API_BASE_URL}${path}`, { ...options, headers });
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response = await fetch(buildRequest(path, options));

  // Access token hết hạn giữa phiên tư vấn: tự gia hạn rồi thử lại đúng 1 lần,
  // thay vì đá Sale ra màn đăng nhập và mất ngữ cảnh đang tư vấn.
  if (response.status === 401 && !path.startsWith("/auth/")) {
    refreshInFlight ??= refreshAccessToken().finally(() => {
      refreshInFlight = null;
    });

    if (await refreshInFlight) {
      response = await fetch(buildRequest(path, options));
    } else {
      clearSession();
    }
  }

  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, detail.detail ?? "Request failed");
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PATCH", body: body ? JSON.stringify(body) : undefined }),
  put: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => apiFetch<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, body: FormData) => apiFetch<T>(path, { method: "POST", body }),
  postUrlEncoded: <T>(path: string, body: URLSearchParams) => apiFetch<T>(path, { method: "POST", body }),
};
