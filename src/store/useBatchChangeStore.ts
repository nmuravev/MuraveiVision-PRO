import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
import { downloadAuthorized } from '../lib/download';
import type { ChangeDetectionResult, ChangeSummary } from './useChangeDetectionStore';

export type BatchChangeStatus = 'idle' | 'running' | 'done' | 'error' | 'aborted';

export type BatchChangePairResult = {
  time_before: number;
  time_after: number;
  method: ChangeDetectionResult['method'];
  aligned?: boolean;
  message?: string | null;
  summary: ChangeSummary;
  matches: ChangeDetectionResult['matches'];
  new: ChangeDetectionResult['new'];
  removed: ChangeDetectionResult['removed'];
  image_diff?: ChangeDetectionResult['image_diff'];
};

export type BatchChangeAggregate = {
  pair_count: number;
  sync_method?: string | null;
  sum_new: number;
  sum_removed: number;
  sum_moved: number;
  sum_stable?: number;
  sum_matched?: number;
  unique_new: number;
  unique_removed: number;
  unique_moved: number;
};

type BatchChangeApiState = {
  task_id: string | null;
  status: BatchChangeStatus;
  progress: number;
  processed: number;
  sample_total: number;
  message: string;
  error: string | null;
  results: BatchChangePairResult[] | null;
  aggregate: BatchChangeAggregate | null;
  sync_method?: string | null;
  pair_count_total?: number;
};

interface BatchChangeStore {
  taskId: string | null;
  status: BatchChangeStatus;
  progress: number;
  processed: number;
  sampleTotal: number;
  message: string;
  error: string | null;
  pairs: BatchChangePairResult[];
  aggregate: BatchChangeAggregate | null;
  syncMethod: string | null;
  videoBefore: string | null;
  videoAfter: string | null;
  exportBusy: boolean;
  exportError: string | null;
  startBatch: (params: {
    videoBefore: string;
    videoAfter: string;
    pairStride: number;
    maxPairs: number;
    useImageFallback: boolean;
    source?: 'auto' | 'tracks' | 'detections';
  }) => Promise<void>;
  abortBatch: () => Promise<void>;
  exportHtml: () => Promise<void>;
  clear: () => void;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function stopPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function applyApi(set: (partial: Partial<BatchChangeStore>) => void, data: BatchChangeApiState) {
  const status = (data.status || 'idle') as BatchChangeStatus;
  set({
    taskId: data.task_id,
    status,
    progress: data.progress ?? 0,
    processed: data.processed ?? 0,
    sampleTotal: data.sample_total ?? 0,
    message: data.message || '',
    error: data.error,
    pairs: Array.isArray(data.results) ? data.results : [],
    aggregate: data.aggregate ?? null,
    syncMethod: data.sync_method ?? null,
  });
  if (status === 'done' || status === 'error' || status === 'aborted') {
    stopPoll();
  }
}

export const useBatchChangeStore = create<BatchChangeStore>((set, get) => ({
  taskId: null,
  status: 'idle',
  progress: 0,
  processed: 0,
  sampleTotal: 0,
  message: '',
  error: null,
  pairs: [],
  aggregate: null,
  syncMethod: null,
  videoBefore: null,
  videoAfter: null,
  exportBusy: false,
  exportError: null,

  clear: () => {
    stopPoll();
    set({
      taskId: null,
      status: 'idle',
      progress: 0,
      processed: 0,
      sampleTotal: 0,
      message: '',
      error: null,
      pairs: [],
      aggregate: null,
      syncMethod: null,
      videoBefore: null,
      videoAfter: null,
      exportBusy: false,
      exportError: null,
    });
  },

  startBatch: async ({
    videoBefore,
    videoAfter,
    pairStride,
    maxPairs,
    useImageFallback,
    source = 'auto',
  }) => {
    stopPoll();
    set({
      status: 'running',
      progress: 0,
      processed: 0,
      sampleTotal: 0,
      message: 'Запуск…',
      error: null,
      pairs: [],
      aggregate: null,
      videoBefore,
      videoAfter,
      exportError: null,
    });
    try {
      const res = await fetch('/api/change-detection/batch', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          video_before: videoBefore,
          video_after: videoAfter,
          source,
          pair_stride: pairStride,
          max_pairs: maxPairs,
          use_image_fallback: useImageFallback,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as BatchChangeApiState & {
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(
          typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`,
        );
      }
      applyApi(set, data);
      const taskId = data.task_id;
      if (!taskId) return;

      pollTimer = setInterval(() => {
        void (async () => {
          try {
            const poll = await fetch(`/api/change-detection/batch/${taskId}`, {
              headers: authHeaders(),
            });
            const body = (await poll.json().catch(() => ({}))) as BatchChangeApiState & {
              detail?: string;
            };
            if (!poll.ok) {
              stopPoll();
              set({
                status: 'error',
                error:
                  typeof body.detail === 'string' ? body.detail : `HTTP ${poll.status}`,
              });
              return;
            }
            applyApi(set, body);
          } catch (e) {
            stopPoll();
            set({
              status: 'error',
              error: e instanceof Error ? e.message : 'Ошибка опроса',
            });
          }
        })();
      }, 500);
    } catch (e) {
      stopPoll();
      set({
        status: 'error',
        error: e instanceof Error ? e.message : 'Ошибка запуска',
        message: '',
      });
    }
  },

  abortBatch: async () => {
    const taskId = get().taskId;
    if (!taskId) return;
    try {
      const res = await fetch(`/api/change-detection/batch/${taskId}/abort`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = (await res.json().catch(() => ({}))) as BatchChangeApiState & {
        detail?: string;
      };
      if (!res.ok) {
        set({
          error: typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`,
        });
        return;
      }
      applyApi(set, data);
    } catch (e) {
      set({
        error: e instanceof Error ? e.message : 'Ошибка отмены',
      });
    }
  },

  exportHtml: async () => {
    const taskId = get().taskId;
    if (!taskId || get().status !== 'done') {
      set({ exportError: 'Нет завершённого batch для экспорта' });
      return;
    }
    set({ exportBusy: true, exportError: null });
    try {
      await downloadAuthorized(`/api/change-detection/batch/${taskId}/export`, {
        filename: 'muravei_batch_change_report.html',
      });
      set({ exportBusy: false });
    } catch (e) {
      set({
        exportBusy: false,
        exportError: e instanceof Error ? e.message : 'Ошибка экспорта',
      });
    }
  },
}));
