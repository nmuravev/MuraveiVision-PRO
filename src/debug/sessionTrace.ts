// KEEP: session trace — do not remove without explicit user order
/**
 * Smart Full-Stack Session Trace (FE).
 * FIFO 500, sanitize secrets/blobs, correlate via X-Muravei-Trace-Id.
 */

export const TRACE_HEADER = 'X-Muravei-Trace-Id';
export const LS_KEY = 'muravei_session_trace';
export const MAX_EVENTS = 500;

export type TraceKind =
  | 'ui.click'
  | 'ui.keydown'
  | 'ui.tab'
  | 'api.req'
  | 'api.res'
  | 'ws.connect'
  | 'ws.close'
  | 'ws.error'
  | 'ws.msg'
  | 'store.change'
  | 'be.log'
  | 'modal'
  | 'note';

export type TraceEvent = {
  id: string;
  ts: number;
  kind: TraceKind;
  traceId: string;
  seq: number;
  summary: string;
  data?: Record<string, unknown>;
};

type Listener = (ev: TraceEvent | null) => void;

const SECRET_KEYS = /^(authorization|token|pin|password|jwt|hub_pin|secret)$/i;
const listeners = new Set<Listener>();

let sessionUuid = '';
let seq = 0;
let recording = true;
let installed = false;
let events: TraceEvent[] = [];
const storeThrottleAt = new Map<string, number>();
let fetchPatched = false;
let originalFetch: typeof window.fetch | null = null;

function uuid(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
  return `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function notify(ev: TraceEvent | null) {
  for (const fn of listeners) {
    try {
      fn(ev);
    } catch {
      /* ignore */
    }
  }
}

export function isTraceRecording(): boolean {
  return recording;
}

export function getTraceSessionId(): string {
  return sessionUuid || '(not-init)';
}

export function nextTraceHeaderValue(): string {
  if (!sessionUuid) sessionUuid = uuid();
  seq += 1;
  return `${sessionUuid}-${seq}`;
}

/** Deep-ish sanitize: strip secrets, truncate strings, drop huge arrays. */
export function sanitizePayload(value: unknown, depth = 0): unknown {
  if (depth > 4) return '[…]';
  if (value == null) return value;
  if (typeof value === 'string') {
    if (value.length > 300) return `${value.slice(0, 300)}…`;
    if (/^data:image\//i.test(value) || value.length > 200 && /^[A-Za-z0-9+/=]{200,}$/.test(value)) {
      return `[blob ${value.length}c]`;
    }
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') return value;
  if (Array.isArray(value)) {
    if (value.length > 20) return `[array len=${value.length}]`;
    return value.slice(0, 8).map((v) => sanitizePayload(v, depth + 1));
  }
  if (typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      if (SECRET_KEYS.test(k)) {
        out[k] = '[redacted]';
        continue;
      }
      out[k] = sanitizePayload(v, depth + 1);
    }
    return out;
  }
  return String(value);
}

export function summarizeJson(value: unknown, max = 300): string {
  try {
    if (value == null) return '';
    if (typeof value === 'string') {
      return value.length > max ? `${value.slice(0, max)}…` : value;
    }
    const s = JSON.stringify(sanitizePayload(value));
    return s.length > max ? `${s.slice(0, max)}…` : s;
  } catch {
    return '[unserializable]';
  }
}

export function addEvent(
  kind: TraceKind,
  summary: string,
  data?: Record<string, unknown>,
): TraceEvent | null {
  if (!recording && kind !== 'note') return null;
  if (!sessionUuid) sessionUuid = uuid();
  seq += 1;
  const ev: TraceEvent = {
    id: `fe-${seq}`,
    ts: Date.now(),
    kind,
    traceId: `${sessionUuid}-${seq}`,
    seq,
    summary: summary.length > 240 ? `${summary.slice(0, 240)}…` : summary,
    data: data ? (sanitizePayload(data) as Record<string, unknown>) : undefined,
  };
  events.push(ev);
  if (events.length > MAX_EVENTS) {
    events = events.slice(-MAX_EVENTS);
  }
  notify(ev);
  return ev;
}

export function addStoreChange(slice: string, summary: string, data?: Record<string, unknown>) {
  const now = Date.now();
  const prev = storeThrottleAt.get(slice) ?? 0;
  if (now - prev < 500) return null;
  storeThrottleAt.set(slice, now);
  return addEvent('store.change', `[${slice}] ${summary}`, data);
}

export function getEvents(): TraceEvent[] {
  return events.slice();
}

export function clearEvents() {
  events = [];
  notify(null);
}

export function setRecording(on: boolean) {
  recording = on;
  try {
    localStorage.setItem(LS_KEY, on ? '1' : '0');
  } catch {
    /* ignore */
  }
  addEvent('note', on ? 'REC on' : 'REC paused (code kept)');
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function exportSessionTraceJson(): string {
  const payload = {
    exportedAt: new Date().toISOString(),
    sessionUuid,
    recording,
    eventCount: events.length,
    events: events.map((e) => ({
      ...e,
      data: e.data ? sanitizePayload(e.data) : undefined,
    })),
  };
  return JSON.stringify(payload, null, 2);
}

export function downloadSessionTraceJson() {
  const text = exportSessionTraceJson();
  const blob = new Blob([text], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `session-trace-${sessionUuid.slice(0, 8)}-${Date.now()}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function cssPath(el: Element): string {
  const parts: string[] = [];
  let cur: Element | null = el;
  for (let i = 0; i < 4 && cur && cur !== document.body; i++) {
    const id = cur.id ? `#${cur.id}` : '';
    const cls =
      typeof cur.className === 'string' && cur.className
        ? `.${cur.className.trim().split(/\s+/).slice(0, 2).join('.')}`
        : '';
    parts.unshift(`${cur.tagName.toLowerCase()}${id}${cls}`);
    cur = cur.parentElement;
  }
  return parts.join('>');
}

function describeClickTarget(el: Element): string {
  const testid = el.getAttribute('data-testid');
  const aria = el.getAttribute('aria-label');
  const text = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  const tag = el.tagName.toLowerCase();
  const id = el.id ? `#${el.id}` : '';
  return [tag + id, testid && `testid=${testid}`, aria && `aria=${aria}`, text && `"${text}"`]
    .filter(Boolean)
    .join(' ');
}

function onClickCapture(ev: MouseEvent) {
  const t = ev.target;
  if (!(t instanceof Element)) return;
  addEvent('ui.click', describeClickTarget(t), {
    path: cssPath(t),
    button: ev.button,
  });
}

function onKeyDownCapture(ev: KeyboardEvent) {
  const tag = (ev.target as HTMLElement | null)?.tagName?.toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  if ((ev.target as HTMLElement | null)?.isContentEditable) return;
  const interesting =
    ev.key === ' ' ||
    ev.key === 'Escape' ||
    ev.key === 'Delete' ||
    ev.key === 'Backspace' ||
    ev.key === 'ArrowLeft' ||
    ev.key === 'ArrowRight' ||
    ev.key === 'f' ||
    ev.key === 'F' ||
    ev.key === 'i' ||
    ev.key === 'I' ||
    ev.key === 'o' ||
    ev.key === 'O' ||
    ev.ctrlKey ||
    ev.metaKey;
  if (!interesting) return;
  addEvent('ui.keydown', `${ev.ctrlKey || ev.metaKey ? 'Ctrl+' : ''}${ev.key}`);
}

function installFetchPatch() {
  if (typeof window === 'undefined' || fetchPatched) return;
  fetchPatched = true;
  originalFetch = window.fetch.bind(window);

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    const isApi = url.includes('/api/') || url.includes('/ws/');
    if (!isApi || !recording) {
      return originalFetch!(input, init);
    }

    const method = (init?.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    const headerVal = nextTraceHeaderValue();
    const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
    if (!headers.has(TRACE_HEADER)) headers.set(TRACE_HEADER, headerVal);

    let bodySummary = '';
    try {
      if (typeof init?.body === 'string' && init.body.length < 4000) {
        try {
          bodySummary = summarizeJson(JSON.parse(init.body));
        } catch {
          bodySummary = summarizeJson(init.body);
        }
      } else if (init?.body instanceof FormData) {
        bodySummary = '[FormData]';
      } else if (init?.body) {
        bodySummary = '[body]';
      }
    } catch {
      bodySummary = '';
    }

    addEvent('api.req', `${method} ${url.split('?')[0]}`, {
      traceHeader: headerVal,
      body: bodySummary || undefined,
    });

    const t0 = performance.now();
    const res = await originalFetch!(input, { ...init, headers });
    const ms = Math.round(performance.now() - t0);

    let resSummary = '';
    try {
      const ct = res.headers.get('content-type') || '';
      if (ct.includes('application/json')) {
        const clone = res.clone();
        const data = await clone.json().catch(() => null);
        if (data && typeof data === 'object') {
          const obj = data as Record<string, unknown>;
          const keys = Object.keys(obj).slice(0, 12);
          const hint: Record<string, unknown> = { keys };
          for (const k of ['status', 'error', 'detail', 'point_count', 'sidecar_missing', 'job_id', 'count', 'ok']) {
            if (k in obj) hint[k] = obj[k];
          }
          if (Array.isArray(obj.detections)) hint.detections_n = obj.detections.length;
          if (Array.isArray(obj.points)) hint.points_n = obj.points.length;
          resSummary = summarizeJson(hint);
        }
      } else if (ct.includes('text/event-stream')) {
        resSummary = '[SSE]';
      } else if (ct.includes('image/') || ct.includes('octet-stream')) {
        resSummary = `[binary ${ct}]`;
      }
    } catch {
      resSummary = '';
    }

    addEvent(
      'api.res',
      `${method} ${url.split('?')[0]} → ${res.status} ${ms}ms`,
      {
        traceHeader: headerVal,
        status: res.status,
        ms,
        summary: resSummary || undefined,
        silent: headers.get('X-Muravei-Silent-Error') === '1',
      },
    );
    return res;
  };
}

function uninstallFetchPatch() {
  if (!fetchPatched || !originalFetch) return;
  window.fetch = originalFetch;
  fetchPatched = false;
  originalFetch = null;
}

function installStoreWatchers() {
  // Lazy imports to avoid circular deps at module load
  void import('../store/useViewerStore').then(({ useViewerStore }) => {
    let prevPath = useViewerStore.getState().viewers['viewer-1']?.sourcePath;
    let prevYolo = useViewerStore.getState().viewers['viewer-1']?.yoloEnabled;
    useViewerStore.subscribe((s) => {
      const v = s.viewers[s.focusedViewerId] || s.viewers['viewer-1'];
      const path = v?.sourcePath;
      if (path !== prevPath) {
        prevPath = path;
        addStoreChange('viewer', `sourcePath=${path || '(none)'}`);
      }
      const yolo = v?.yoloEnabled;
      if (yolo !== prevYolo) {
        prevYolo = yolo;
        addStoreChange('viewer', `yoloEnabled=${yolo}`);
      }
    });
  });
  void import('../store/useReconStore').then(({ useReconStore }) => {
    let prevRun = useReconStore.getState().reconRunning;
    let prevPhase = useReconStore.getState().reconPhase;
    useReconStore.subscribe((s) => {
      if (s.reconRunning !== prevRun || s.reconPhase !== prevPhase) {
        prevRun = s.reconRunning;
        prevPhase = s.reconPhase;
        addStoreChange(
          'recon',
          `running=${s.reconRunning} phase=${s.reconPhase || '-'} ${s.reconProgress ?? 0}%`,
          { message: s.reconMessage },
        );
      }
    });
  });
  void import('../store/useMuraveiStore').then(({ useMuraveiStore }) => {
    let prevN = useMuraveiStore.getState().detections.length;
    let prevHydrated = useMuraveiStore.getState().hydratedSourceVideo;
    useMuraveiStore.subscribe((s) => {
      if (s.hydratedSourceVideo !== prevHydrated) {
        prevHydrated = s.hydratedSourceVideo;
        addStoreChange('muravei', `hydrated=${s.hydratedSourceVideo || '(none)'}`);
      }
      if (s.detections.length !== prevN) {
        prevN = s.detections.length;
        addStoreChange('muravei', `detections=${s.detections.length}`);
      }
    });
  });
  void import('../store/usePanelLayoutStore').then(({ usePanelLayoutStore }) => {
    let prevMode = usePanelLayoutStore.getState().workspaceMode;
    usePanelLayoutStore.subscribe((s) => {
      if (s.workspaceMode !== prevMode) {
        prevMode = s.workspaceMode;
        addStoreChange('layout', `workspaceMode=${s.workspaceMode}`);
        addEvent('ui.tab', `workspaceMode=${s.workspaceMode}`);
      }
    });
  });
  void import('../store/useBatchScanStore').then(({ useBatchScanStore }) => {
    let prevStatus = useBatchScanStore.getState().status;
    useBatchScanStore.subscribe((s) => {
      if (s.status !== prevStatus) {
        prevStatus = s.status;
        addStoreChange('batchScan', `status=${s.status}`);
      }
    });
  }).catch(() => {
    /* optional store */
  });
}

export function initSessionTrace(): () => void {
  if (typeof window === 'undefined') return () => undefined;
  if (installed) return () => undefined;
  installed = true;
  sessionUuid = uuid();
  seq = 0;
  try {
    const raw = localStorage.getItem(LS_KEY);
    // default ON when unset
    recording = raw !== '0';
  } catch {
    recording = true;
  }

  document.addEventListener('click', onClickCapture, true);
  document.addEventListener('keydown', onKeyDownCapture, true);
  installFetchPatch();
  installStoreWatchers();

  const onModal = (event: Event) => {
    const detail = (event as CustomEvent).detail;
    addEvent(
      'modal',
      `ErrorDetails ${detail?.code ?? ''} ${detail?.title || detail?.message || ''}`.trim(),
      { name: detail?.name, message: detail?.message },
    );
  };
  window.addEventListener('muravei:show-error-modal', onModal);

  addEvent('note', `Session trace init session=${sessionUuid.slice(0, 8)} rec=${recording}`);

  const w = window as unknown as Record<string, unknown>;
  w.__muraveiSessionTrace = {
    getEvents,
    clear: clearEvents,
    exportJson: exportSessionTraceJson,
    download: downloadSessionTraceJson,
    pause: () => setRecording(false),
    resume: () => setRecording(true),
    isRecording: isTraceRecording,
    sessionId: getTraceSessionId,
    addNote: (msg: string) => addEvent('note', msg),
    addWs: (
      kind: 'ws.connect' | 'ws.close' | 'ws.error' | 'ws.msg',
      summary: string,
      data?: Record<string, unknown>,
    ) => addEvent(kind, summary, data),
  };

  return () => {
    document.removeEventListener('click', onClickCapture, true);
    document.removeEventListener('keydown', onKeyDownCapture, true);
    window.removeEventListener('muravei:show-error-modal', onModal);
    uninstallFetchPatch();
    installed = false;
  };
}

/** Helper for Viewer WS instrumentation */
export function traceWs(
  kind: 'ws.connect' | 'ws.close' | 'ws.error' | 'ws.msg',
  summary: string,
  data?: Record<string, unknown>,
) {
  addEvent(kind, summary, data);
}
