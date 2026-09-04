/** Structured API error payload from backend error_catalog. */

export type ApiErrorDetails = {
  code: number;
  name: string;
  title: string;
  message: string;
  causes: string[];
  solutions: string[];
  examples?: string[];
  docs_url?: string;
};

export const SHOW_ERROR_MODAL_EVENT = 'muravei:show-error-modal';
export const SILENT_API_ERROR_HEADER = 'X-Muravei-Silent-Error';

type ErrorBody = {
  detail?: unknown;
  error?: Partial<ApiErrorDetails> & { causes?: unknown; solutions?: unknown };
};

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

export function parseApiErrorBody(data: unknown, fallbackStatus = 0): ApiErrorDetails | null {
  if (!data || typeof data !== 'object') return null;
  const body = data as ErrorBody;
  const err = body.error;
  if (!err || typeof err !== 'object') return null;
  const causes = asStringList(err.causes);
  const solutions = asStringList(err.solutions);
  if (causes.length === 0 && solutions.length === 0) return null;

  const detailMsg =
    typeof body.detail === 'string'
      ? body.detail
      : typeof err.message === 'string'
        ? err.message
        : '';

  return {
    code: typeof err.code === 'number' ? err.code : fallbackStatus,
    name: typeof err.name === 'string' ? err.name : 'UNKNOWN',
    title: typeof err.title === 'string' ? err.title : 'Ошибка',
    message: typeof err.message === 'string' && err.message ? err.message : detailMsg,
    causes,
    solutions,
    examples: asStringList(err.examples),
    docs_url: typeof err.docs_url === 'string' ? err.docs_url : undefined,
  };
}

export function emitApiError(details: ApiErrorDetails): void {
  window.dispatchEvent(new CustomEvent(SHOW_ERROR_MODAL_EVENT, { detail: details }));
}

/** Read enriched error from a failed Response (does not consume caller's body if clone used). */
export async function emitApiErrorFromResponse(response: Response): Promise<boolean> {
  if (response.ok) return false;
  try {
    const data: unknown = await response.clone().json();
    const details = parseApiErrorBody(data, response.status);
    if (!details) return false;
    emitApiError(details);
    return true;
  } catch {
    return false;
  }
}

let fetchPatched = false;
let lastEmitKey = '';
let lastEmitAt = 0;

function requestHasSilentHeader(init?: RequestInit): boolean {
  const headers = init?.headers;
  if (!headers) return false;
  if (headers instanceof Headers) {
    return headers.get(SILENT_API_ERROR_HEADER) === '1';
  }
  if (Array.isArray(headers)) {
    return headers.some(
      ([k, v]) =>
        k.toLowerCase() === SILENT_API_ERROR_HEADER.toLowerCase() && String(v) === '1',
    );
  }
  const record = headers as Record<string, string>;
  return (
    record[SILENT_API_ERROR_HEADER] === '1' ||
    record['x-muravei-silent-error'] === '1'
  );
}

function shouldSkipApiErrorReport(url: string, status: number, init?: RequestInit): boolean {
  if (requestHasSilentHeader(init)) return true;
  if (status === 409 && url.includes('/api/recon/start')) return true;
  if (status === 409 && url.includes('/api/recon/train/start')) return true;
  if (status !== 404) return false;
  if (url.includes('/api/recon/asset/')) return true;
  if (url.includes('/api/geo/import')) return true;
  return false;
}

/**
 * Patch window.fetch once: when a non-OK /api response carries structured ``error``,
 * show the field diagnostics modal. Keeps existing callers unchanged.
 */
export function installApiErrorReporter(): () => void {
  if (typeof window === 'undefined' || fetchPatched) {
    return () => undefined;
  }
  fetchPatched = true;
  const original = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const response = await original(input, init);
    if (!response.ok) {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      if (
        url.includes('/api/') &&
        !shouldSkipApiErrorReport(url, response.status, init)
      ) {
        void (async () => {
          try {
            const data: unknown = await response.clone().json();
            const details = parseApiErrorBody(data, response.status);
            if (!details) return;
            const key = `${details.code}:${details.message}`;
            const now = Date.now();
            if (key === lastEmitKey && now - lastEmitAt < 2000) return;
            lastEmitKey = key;
            lastEmitAt = now;
            emitApiError(details);
          } catch {
            /* non-JSON error bodies stay silent */
          }
        })();
      }
    }
    return response;
  };

  return () => {
    window.fetch = original;
    fetchPatched = false;
  };
}
