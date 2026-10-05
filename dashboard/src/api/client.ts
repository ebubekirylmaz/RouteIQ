import type { components } from "./schema";

/** Generated from the OpenAPI schema: `npm run api:types`. */
export type Schemas = components["schemas"];

/** A non-2xx answer. `detail` is the API's own message, e.g. "request is not pending review". */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const { detail } = body as { detail: unknown };
      // FastAPI answers 422 validation errors with a list, our own errors with a string.
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) return "invalid request";
    }
  } catch {
    // not JSON, fall through
  }
  return response.statusText || "request failed";
}

export type ApiResult<T> = { data: T; headers: Headers };

async function request<T>(path: string, init: RequestInit = {}): Promise<ApiResult<T>> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body !== undefined) headers.set("Content-Type", "application/json");

  const response = await fetch(path, { ...init, headers });
  if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
  return { data: (await response.json()) as T, headers: response.headers };
}

export const apiGet = <T>(path: string, signal?: AbortSignal) =>
  request<T>(path, { method: "GET", signal });

export const apiPost = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/** The number of matching rows, ignoring paging (`X-Total-Count`). */
export function totalCount(headers: Headers): number {
  const value = Number(headers.get("X-Total-Count"));
  return Number.isFinite(value) ? value : 0;
}

/** Builds `?a=1&b=2` and leaves out empty values. */
export function queryString(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
