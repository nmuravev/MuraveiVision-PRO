import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
import { useSam3Store } from './useSam3Store';

export type BatchSegMask = {
  class: string;
  conf: number;
  polygon_norm: number[][];
};

export type BatchSegFrame = {
  time_sec: number;
  masks: BatchSegMask[];
};

export type BatchSegStatus = 'idle' | 'running' | 'done' | 'error' | 'aborted';

type BatchSegApiState = {
  task_id: string | null;
  status: BatchSegStatus;
  progress: number;
  processed: number;
  sample_total: number;
  mask_total: number;
  message: string;
  error: string | null;
  results: BatchSegFrame[] | null;
  sam_unloaded?: boolean;
};

interface BatchSegStore {
  taskId: string | null;
  status: BatchSegStatus;
  progress: number;
  processed: number;
  sampleTotal: number;
  maskTotal: number;
  message: string;
  error: string | null;
  frames: BatchSegFrame[];
  samUnloaded: boolean;
  startBatch: (params: {
    videoPath: string;
    frameStep: number;
    confidence: number;
  }) => Promise<void>;
  abortBatch: () => Promise<void>;
  clear: () => void;
}

let pollTimer: ReturnType<typeof setInterval> | null = null;

function stopPoll() {
  if (pollTimer != null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function applyApi(set: (partial: Partial<BatchSegStore>) => void, data: BatchSegApiState) {
  const status = (data.status || 'idle') as BatchSegStatus;
  const samUnloaded = Boolean(data.sam_unloaded);
  set({
    taskId: data.task_id,
    status,
    progress: data.progress ?? 0,
    processed: data.processed ?? 0,
    sampleTotal: data.sample_total ?? 0,
    maskTotal: data.mask_total ?? 0,
    message: data.message || '',
    error: data.error,
    frames: Array.isArray(data.results) ? data.results : [],
    ...(data.sam_unloaded != null ? { samUnloaded } : {}),
  });
  if (samUnloaded) {
    useSam3Store.getState().markUnloadedForBatch();
  }
  if (status === 'done' || status === 'error' || status === 'aborted') {
    stopPoll();
  }
}

export const useBatchSegStore = create<BatchSegStore>((set, get) => ({
  taskId: null,
  status: 'idle',
  progress: 0,
  processed: 0,
  sampleTotal: 0,
  maskTotal: 0,
  message: '',
  error: null,
  frames: [],
  samUnloaded: false,

  clear: () => {
    stopPoll();
    set({
      taskId: null,
      status: 'idle',
      progress: 0,
      processed: 0,
      sampleTotal: 0,
      maskTotal: 0,
      message: '',
      error: null,
      frames: [],
      samUnloaded: false,
    });
  },

  startBatch: async ({ videoPath, frameStep, confidence }) => {
    stopPoll();
    set({
      status: 'running',
      progress: 0,
      processed: 0,
      sampleTotal: 0,
      maskTotal: 0,
      message: 'Запуск…',
      error: null,
      frames: [],
      samUnloaded: false,
    });
    try {
      const res = await fetch('/api/seg/batch', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          video_path: videoPath,
          frame_step: frameStep,
          confidence,
        }),
      });
      const data = (await res.json().catch(() => ({}))) as BatchSegApiState & {
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
            const poll = await fetch(`/api/seg/batch/${taskId}`, {
              headers: authHeaders(),
            });
            const body = (await poll.json().catch(() => ({}))) as BatchSegApiState & {
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
      }, 1000);
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
      const res = await fetch(`/api/seg/batch/${taskId}/abort`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = (await res.json().catch(() => ({}))) as BatchSegApiState & {
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
}));
