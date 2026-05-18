/**
 * Thin fetch wrapper for the SelfRepair `/v1` API.
 *
 * Centralises base URL, credential mode, JSON encoding, error normalisation
 * and the dev org-pin header so screen-level code never touches `fetch`
 * directly. Uses native fetch; no axios/ky to keep the bundle small.
 *
 * Cookies are always sent (`credentials: 'include'`) so the session
 * middleware can resolve `request.state.session_*`. The dev org pin is
 * forwarded as a header so single-tenant local runs work without a
 * login round-trip.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const DEV_ORG_ID = import.meta.env.VITE_DEV_ORG_ID || "";

export class ApiError extends Error {
  constructor(status, body, request) {
    super(
      `[${request.method} ${request.url}] ${status} ${
        typeof body === "string" ? body : JSON.stringify(body)
      }`,
    );
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    this.request = request;
  }

  /** Convenience for screens: read `error.detail` like FastAPI returns. */
  get detail() {
    if (this.body && typeof this.body === "object" && this.body.detail) {
      return this.body.detail;
    }
    return this.message;
  }
}

function buildHeaders(extra) {
  const h = {
    Accept: "application/json",
    ...(extra || {}),
  };
  if (DEV_ORG_ID && !h["X-SelfRepair-Org-Id"]) {
    h["X-SelfRepair-Org-Id"] = DEV_ORG_ID;
  }
  return h;
}

export function qs(params) {
  if (!params) return "";
  const s = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) {
      for (const item of v) s.append(k, String(item));
    } else {
      s.set(k, String(v));
    }
  }
  const out = s.toString();
  return out ? `?${out}` : "";
}

export async function api(path, options = {}) {
  const { method = "GET", body, headers, signal } = options;
  const url = `${API_BASE}${path}`;
  const init = {
    method,
    credentials: "include",
    headers: buildHeaders({
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers || {}),
    }),
    signal,
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(url, init);
  } catch (err) {
    // Network-level failure (DNS, TLS, server down) is not an HTTP
    // error. Translate into ApiError with status=0 so React Query's
    // retry logic treats it as transient.
    throw new ApiError(0, err.message || "network error", { url, method });
  }

  if (res.status === 204) return null;
  const contentType = res.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  let payload = null;
  if (isJson) {
    try {
      payload = await res.json();
    } catch {
      payload = null;
    }
  } else if (contentType.startsWith("text/")) {
    payload = await res.text();
  }
  if (!res.ok) {
    throw new ApiError(res.status, payload, { url, method });
  }
  return payload;
}

export const apiBase = API_BASE;
