import { create } from 'zustand';
import { readSse } from '../lib/readSse';
import { authHeaders } from './useMuraveiStore';

/** Timeout for waiting scanner idle (ms). Configurable for field tuning. */
export const SCAN_IDLE_TIMEOUT_MS = 6000;

export type BatchScanStatus = 'idle' | 'running' | 'done' | 'error';

type HydrateFn = (sourceVideo?: string | null) => Promise<void>;

export type BatchScanStartOpts = {
  tStart?: number;
  tEnd?: number;
  fpsSample?: number;
  conf?: number;
};

interface BatchScanState {
  status: BatchScanStatus;
  message: string;
  phase: string | null;
  processed: number;
  sampleTotal: number;
  found: number;
  videoPath: string | null;
  errorTimeout: string | null;
  startScan: (
    videoPath: string,
    hydrateDetections: HydrateFn,
    opts?: BatchScanStartOpts,
  ) => Promise<void>;
  stopScan: () => Promise<void>;
  reset: () => void;
}

let scanAbort: AbortController | null = null;

function stopScanStream(): void {
  scanAbort?.abort();
  scanAbort = null;
}

async function waitScanIdle(
  onError: (msg: string) => void,
): Promise<void> {
  const deadline = Date.now() + SCAN_IDLE_TIMEOUT_MS;
  let done = false;
  while (!done && Date.now() < deadline) {
    try {
      const res = await fetch('/api/scan/status', { headers: authHeaders() });
      if (!res.ok) {
        return;
      }
      const st = (await res.json()) as { status?: string };
      if (st.status !== 'running') {
        return;
      }
    } catch (_err) {
      return;
    }
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, 350);
    });
  }
  // Timeout reached — signal explicit error instead of silent fail
  onError('Сканер не остановился вовремя. Проверьте оборудование или нажмите "Стоп".');
}

export const useBatchScanStore = create<BatchScanState>((set, get) => ({
  status: 'idle',
  message: '',
  phase: null,
  processed: 0,
  sampleTotal: 0,
  found: 0,
  videoPath: null,
  errorTimeout: null,

  reset: () => {
    stopScanStream();
    set({
      status: 'idle',
      message: '',
      phase: null,
      processed: 0,
      sampleTotal: 0,
      found: 0,
      videoPath: null,
      errorTimeout: null,
    });
  },

  stopScan: async () => {
    stopScanStream();
    set({ message: 'Остановка…', errorTimeout: null });
    await fetch('/api/scan/stop', { method: 'POST', headers: authHeaders() });
    await waitScanIdle((msg) => set({ errorTimeout: msg }));
  },

  startScan: async (videoPath, hydrateDetections, opts) => {
    const cur = get();
    if (cur.status === 'running' && cur.videoPath === videoPath) {
      return;
    }

    if (cur.status === 'running') {
      await get().stopScan();
      await waitScanIdle((msg) => set({ errorTimeout: msg }));
    }

    stopScanStream();

    const body: Record<string, unknown> = {
      video_path: videoPath,
      fps_sample: opts?.fpsSample ?? 2.0,
      conf: opts?.conf ?? 0.25,
      save_crops: true,
    };
    if (opts?.tStart != null && opts.tStart >= 0) {
      body.t_start = opts.tStart;
    }
    if (opts?.tEnd != null && opts.tEnd > 0) {
      body.t_end = opts.tEnd;
    }

    const res = await fetch('/api/scan/start', {
      method: 'POST',
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data.detail === 'string' ? data.detail : 'Не удалось запустить скан';
      set({
        status: 'error',
        message: detail,
        phase: 'error',
        videoPath: videoPath,
      });
      throw new Error(detail);
    }

    set({
      status: (data.status as BatchScanStatus) || 'running',
      message: typeof data.message === 'string' ? data.message : 'Сканирование…',
      phase: 'opening',
      processed: 0,
      sampleTotal: 0,
      found: 0,
      videoPath: videoPath,
    });

    const abort = new AbortController();
    scanAbort = abort;

    try {
      await readSse(
        '/api/scan/stream',
        (ev) => {
          const patch: Partial<BatchScanState> = {};
          if (typeof ev.status === 'string') {
            patch.status = ev.status as BatchScanStatus;
          }
          if (typeof ev.message === 'string') {
            patch.message = ev.message;
          }
          if (typeof ev.phase === 'string') {
            patch.phase = ev.phase;
          }
          if (typeof ev.processed === 'number') {
            patch.processed = ev.processed;
          }
          if (typeof ev.sample_total === 'number') {
            patch.sampleTotal = ev.sample_total;
          } else if (typeof ev.total_frames === 'number') {
            patch.sampleTotal = ev.total_frames;
          }
          if (typeof ev.detections_found === 'number') {
            patch.found = ev.detections_found;
          }
          if (Object.keys(patch).length) {
            set(patch);
          }

          if (ev.status === 'done') {
            void hydrateDetections(videoPath);
            const src = typeof ev.source_video === 'string' ? ev.source_video : null;
            if (src && src !== videoPath) {
              void hydrateDetections(src);
            }
          }
          if (ev.status === 'done' || ev.status === 'error') {
            stopScanStream();
          }
        },
        abort,
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return;
      }
      set({
        status: 'error',
        message: err instanceof Error ? err.message : 'Ошибка скана',
        phase: 'error',
      });
      throw err;
    } finally {
      if (scanAbort === abort) {
        scanAbort = null;
      }
    }
  },
}));

export function batchScanProgressPct(state: {
  status: BatchScanStatus;
  processed: number;
  sampleTotal: number;
}): number {
  if (state.status === 'done') {
    return 100;
  }
  if (state.sampleTotal > 0) {
    return Math.min(100, Math.round((state.processed / state.sampleTotal) * 100));
  }
  if (state.status === 'running') {
    return Math.min(95, 5 + state.processed);
  }
  return 0;
}
