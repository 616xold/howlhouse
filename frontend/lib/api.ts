const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const RAW_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL;
export const IDENTITY_TOKEN_STORAGE_KEY = "howlhouse_identity_token";

export const API_BASE_URL = RAW_API_BASE_URL.replace(/\/$/, "");
const API_BASE_IS_RELATIVE = API_BASE_URL.startsWith("/");

export function apiUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  if (API_BASE_IS_RELATIVE) {
    if (path.startsWith("/")) {
      return `${API_BASE_URL}${path}`;
    }
    return `${API_BASE_URL}/${path}`;
  }

  if (path.startsWith("/")) {
    return `${API_BASE_URL}${path}`;
  }
  return `${API_BASE_URL}/${path}`;
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const retryAfter = response.headers.get("Retry-After");
    if (typeof body?.detail === "string") {
      if (retryAfter && response.status === 429) {
        return `${body.detail} (retry after ${retryAfter}s)`;
      }
      return body.detail;
    }
    const payload = JSON.stringify(body);
    if (retryAfter && response.status === 429) {
      return `${payload} (retry after ${retryAfter}s)`;
    }
    return payload;
  } catch {
    const retryAfter = response.headers.get("Retry-After");
    if (retryAfter && response.status === 429) {
      return `${response.status} ${response.statusText} (retry after ${retryAfter}s)`;
    }
    return `${response.status} ${response.statusText}`;
  }
}

export function getStoredIdentityToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const value = window.localStorage.getItem(IDENTITY_TOKEN_STORAGE_KEY);
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

export function setStoredIdentityToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (!token) {
    window.localStorage.removeItem(IDENTITY_TOKEN_STORAGE_KEY);
    return;
  }
  window.localStorage.setItem(IDENTITY_TOKEN_STORAGE_KEY, token.trim());
}

export function buildAuthHeaders(initHeaders?: HeadersInit): Headers {
  const headers = new Headers(initHeaders);
  const token = getStoredIdentityToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = buildAuthHeaders(init?.headers);
  headers.set("Content-Type", "application/json");
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return (await response.json()) as T;
}

export async function fetchText(path: string, init?: RequestInit): Promise<string> {
  const headers = buildAuthHeaders(init?.headers);
  const response = await fetch(apiUrl(path), {
    ...init,
    headers,
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(await readErrorMessage(response));
  }
  return response.text();
}
