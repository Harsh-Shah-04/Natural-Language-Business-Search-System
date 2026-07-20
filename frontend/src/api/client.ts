// Base HTTP client. Centralises the API base URL, JSON handling, and error
// normalisation so endpoint modules (see search.ts) stay thin.

/**
 * Base URL of the FastAPI backend. Configurable via VITE_API_BASE_URL so a
 * deploy points at the hosted API without code changes; defaults to the local
 * uvicorn address for development.
 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

/** Thrown for any non-2xx response or network/parse failure. */
export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Extract a human-readable message from FastAPI's error body. FastAPI puts a
 * string in `detail` for HTTPException (e.g. the 422 from an invalid filter),
 * or an array of validation errors for request-shape failures.
 */
function messageFromDetail(body: unknown, fallback: string): string {
  if (body && typeof body === 'object' && 'detail' in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (first && typeof first === 'object' && 'msg' in first) {
        return String((first as { msg: unknown }).msg);
      }
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch {
    // fetch rejects on network errors, DNS failures, and CORS blocks — none of
    // which carry an HTTP status.
    throw new ApiError(
      'Could not reach the search service. Is the backend running?',
      null,
    );
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Some error responses may have no/!JSON body; leave body null.
  }

  if (!response.ok) {
    throw new ApiError(
      messageFromDetail(body, `Request failed (${response.status})`),
      response.status,
    );
  }

  return body as T;
}

export const apiClient = { request };
