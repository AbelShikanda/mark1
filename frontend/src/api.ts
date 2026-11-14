/// <reference types="vite/client" />
import axios from 'axios';

// Same-origin by default: the FastAPI server also serves the built UI.
// Dev mode sets VITE_API_BASE=http://localhost:8000 in .env.development.
export const API_BASE = import.meta.env.VITE_API_BASE ?? '';

export const api = axios.create({ baseURL: API_BASE });

// A stale backend (started before the latest routes were added) answers unknown
// API paths with index.html. Surface that as a clear message instead of letting
// the UI fail with confusing parse errors.
api.interceptors.response.use(
  (response) => {
    const contentType = String(response.headers?.['content-type'] ?? '');
    if (contentType.includes('text/html') && typeof response.data === 'string') {
      return Promise.reject(
        new Error(
          'The server is returning the web page instead of data. Restart the backend so the latest API routes load, then try again.',
        ),
      );
    }
    return response;
  },
  (error) => Promise.reject(error),
);

type DetailItem = { msg?: string; loc?: (string | number)[] };

/** Turn any axios/network failure into a message the user can actually read. */
export function getErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: unknown } | undefined;
    const detail = data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item: DetailItem) => {
          const field = item.loc?.filter((part) => part !== 'body').join('.');
          return field ? `${field}: ${item.msg ?? 'invalid value'}` : item.msg ?? 'invalid value';
        })
        .join('; ');
    }
    if (error.response) return `Request failed (HTTP ${error.response.status})`;
    return error.message || 'Cannot reach the server. Is the backend running?';
  }
  return error instanceof Error ? error.message : 'Something went wrong';
}
