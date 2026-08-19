// Dedicated fetch wrapper for the public/customer chat endpoints (backend/routers/customer_chat.py).
//
// Kept separate from api/client.ts rather than folded into it: that client always attaches
// the Sale/Admin/Customer `Authorization` header from `access_token` and nothing else, while
// this flow must also work for a visitor with no account at all — those calls carry an
// `X-Visitor-Token` header instead, sourced from useVisitorToken's localStorage cache. Mixing
// both header schemes into the generic client used everywhere else in the app would make the
// common case harder to reason about for no benefit.

import { getVisitorSession } from "../hooks/useVisitorToken";
import { extractErrorMessage } from "./errorMessage";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export class CustomerApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("access_token");
  const role = localStorage.getItem("role");
  if (token && role === "customer") return { Authorization: `Bearer ${token}` };

  const visitor = getVisitorSession();
  return visitor ? { "X-Visitor-Token": visitor.visitorToken } : {};
}

async function customerFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  for (const [key, value] of Object.entries(authHeaders())) headers.set(key, value);

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new CustomerApiError(response.status, extractErrorMessage(body, response.statusText || "Request failed"));
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const customerApi = {
  get: <T>(path: string) => customerFetch<T>(path),
  post: <T>(path: string, body?: unknown) =>
    customerFetch<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => customerFetch<T>(path, { method: "DELETE" }),
};
