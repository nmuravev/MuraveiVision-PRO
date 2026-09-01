import { create } from 'zustand';
import { readSse } from '../lib/readSse';
import { authHeaders } from './useMuraveiStore';

export type BatchScanStatus = 'idle' | 'running' | 'done' | 'error';

type HydrateFn = (sourceVideo?: string | null) => Promise<void>;

interface BatchScanState {
  status: BatchScanStatus;
  message: string;
  processed: number;
  sampleTotal: number;
  found: number;
  videoPath: string | null;
  startScan: (videoPath: string, hydrateDetections: HydrateFn) => Promise<void>;
  stopScan: () => Promise<void>;
  reset: () => void;
}

let scanAbort: AbortController | null = null;

function stopScanStream() {
  scanAbort?.abort();
  scanAbort = null;
}

export const useBatchScanStore = create<BatchScanState>((set, get) => ({
  status: 'idle',
  message: '',
  processed: 0,
  sampleTotal: 0,
  found: 0,
  videoPath: null,

  reset: () => {
    stopScanStream();
    set({
      status: 'idle',
      message: '',
      processed: 0,
      sampleTotal: 0,
      found: 0,
      videoPath: null,
    });
  },

  stopScan: async () => {
    stopScanStream();
    set({ message: 'Остановка…' });
    await fetch('/api/scan/stop', { method: 'POST', headers: authHeaders() });
  },

  startScan: async (videoPath, hydrateDetections) => {
    const cur = get();
    if (cur.status === 'running' && cur.videoPath === videoPath) return;

    if (cur.status === 'running' && cur.videoPath !== videoPath) {
      await get().stopScan();
    }

    stopScanStream();
    set({
      status: 'running',
      message: 'Запуск…',
      processed: 0,
      sampleTotal: 0,
      found: 0,
      videoPath,
    });

    const res = await fetch('/api/scan/start', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        video_path: videoPath,
        fps_sample: 1.0,
        conf: 0.25,
        save_crops: true,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail =
        typeof data.detail === 'string' ? data.detail : 'Не удалось запустить скан';
      set({ status: 'error', message: detail });
      throw new Error(detail);
    }

    set({
      status: (data.status as BatchScanStatus) || 'running',
      message: typeof data.message === 'string' ? data.message : 'Сканирование…',
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
          if (typeof ev.message === 'string') patch.message = ev.message;
          if (typeof ev.processed === 'number') patch.processed = ev.processed;
          if (typeof ev.sample_total === 'number') patch.sampleTotal = ev.sample_total;
          else if (typeof ev.total_frames === 'number') patch.sampleTotal = ev.total_frames;
          if (typeof ev.detections_found === 'number') patch.found = ev.detections_found;
          if (Object.keys(patch).length) set(patch);

          if (ev.status === 'done') {
            void hydrateDetections(videoPath);
            const src = typeof ev.source_video === 'string' ? ev.source_video : null;
            if (src && src !== videoPath) void hydrateDetections(src);
          }
          // Unsubscribe on terminal states only — idle must not tear down / reconnect.
          if (ev.status === 'done' || ev.status === 'error') {
            stopScanStream();
          }
        },
        abort,
      );
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      set({
        status: 'error',
        message: err instanceof Error ? err.message : 'Ошибка скана',
      });
      throw err;
    } finally {
      if (scanAbort === abort) scanAbort = null;
    }
  },
}));

export function batchScanProgressPct(state: {
  status: BatchScanStatus;
  processed: number;
  sampleTotal: number;
}): number {
  if (state.status === 'done') return 100;
  if (state.sampleTotal > 0) {
    return Math.min(100, Math.round((state.processed / state.sampleTotal) * 100));
  }
  if (state.status === 'running') {
    return Math.min(95, 5 + state.processed);
  }
  return 0;
}
