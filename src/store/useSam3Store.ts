import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';

export type Sam3Tool = 'none' | 'point';

export type Sam3Mask = {
  class: string;
  conf: number;
  polygon_norm: number[][];
};

export type Sam3Prompt = {
  points?: { x: number; y: number; label: number }[];
  bboxes?: { x1: number; y1: number; x2: number; y2: number }[];
  text?: string[];
};

export function parseSam3TextPrompt(raw: string): string[] {
  return raw
    .split(';')
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 3);
}

export type Sam3PropFrame = {
  time_sec: number;
  frame_idx?: number;
  masks: Sam3Mask[];
};

export type Sam3PropStatus = 'idle' | 'running' | 'done' | 'error' | 'aborted';

type PropApiState = {
  task_id: string | null;
  status: Sam3PropStatus;
  progress: number;
  processed: number;
  sample_total: number;
  mask_total: number;
  persisted?: number;
  message: string;
  error: string | null;
  results: Sam3PropFrame[] | null;
  // P3.13.3d: full-video chunking state
  full_video?: boolean;
  total_windows?: number;
  current_window?: number;
};

interface Sam3State {
  ready: boolean;
  loaded: boolean;
  weight: string | null;
  busy: boolean;
  tool: Sam3Tool;
  hint: string;
  cpuEtaShow: boolean;
  cpuEtaRu: string;
  lastUnloadNotice: string | null;
  lastPrompt: Sam3Prompt | null;
  textPrompt: string;
  persistEnabled: boolean;
  fullVideoEnabled: boolean;  // P3.13.3d: P1 own checkbox state
  propTaskId: string | null;
  propStatus: Sam3PropStatus;
  propProgress: number;
  propProcessed: number;
  propSampleTotal: number;
  propMaskTotal: number;
  propPersisted: number;
  propMessage: string;
  propError: string | null;
  propFrames: Sam3PropFrame[];
  propTotalWindows: number;  // P3.13.3d
  propCurrentWindow: number;  // P3.13.3d
  refreshStatus: () => Promise<void>;
  load: () => Promise<{ yoloSegUnloaded: boolean }>;
  unload: () => Promise<void>;
  setTool: (t: Sam3Tool) => void;
  setHint: (hint: string) => void;
  clearNotice: () => void;
  dismissCpuEta: () => Promise<void>;
  markUnloadedForBatch: () => void;
  markUnloadedByYolo: () => void;
  setPersistEnabled: (v: boolean) => void;
  setFullVideoEnabled: (v: boolean) => void;  // P3.13.3d: P1
  setTextPrompt: (v: string) => void;
  setLastPrompt: (p: Sam3Prompt | null) => void;
  clearPropagate: () => void;
  startPropagate: (params: {
    videoPath: string;
    timeSec: number;
    maxFrames?: number;
    persist?: boolean;
    fullVideo?: boolean;  // P3.13.3d
  }) => Promise<void>;
  abortPropagate: () => Promise<void>;
  infer: (params: {
    imageBase64: string;
    points?: { x: number; y: number; label: number }[];
    bboxes?: { x1: number; y1: number; x2: number; y2: number }[];
    text?: string[];
  }) => Promise<Sam3Mask[]>;
}

let propPoll: ReturnType<typeof setInterval> | null = null;

function stopPropPoll() {
  if (propPoll != null) {
    clearInterval(propPoll);
    propPoll = null;
  }
}

function applyProp(set: (partial: Partial<Sam3State>) => void, data: PropApiState) {
  const status = (data.status || 'idle') as Sam3PropStatus;
  set({
    propTaskId: data.task_id,
    propStatus: status,
    propProgress: data.progress ?? 0,
    propProcessed: data.processed ?? 0,
    propSampleTotal: data.sample_total ?? 0,
    propMaskTotal: data.mask_total ?? 0,
    propPersisted: data.persisted ?? 0,
    propMessage: data.message || '',
    propError: data.error,
    propFrames: Array.isArray(data.results) ? data.results : [],
    // P3.13.3d: window state
    propTotalWindows: data.total_windows ?? 0,
    propCurrentWindow: data.current_window ?? 0,
  });
  if (status === 'done' || status === 'error' || status === 'aborted') {
    stopPropPoll();
  }
}

export const useSam3Store = create<Sam3State>((set, get) => ({
  ready: false,
  loaded: false,
  weight: null,
  busy: false,
  tool: 'none',
  hint: '',
  cpuEtaShow: false,
  cpuEtaRu: '',
  lastUnloadNotice: null,
  lastPrompt: null,
  textPrompt: '',
  persistEnabled: false,
  fullVideoEnabled: false,  // P3.13.3d: P1
  propTaskId: null,
  propStatus: 'idle',
  propProgress: 0,
  propProcessed: 0,
  propSampleTotal: 0,
  propMaskTotal: 0,
  propPersisted: 0,
  propMessage: '',
  propError: null,
  propFrames: [],
  propTotalWindows: 0,  // P3.13.3d
  propCurrentWindow: 0,  // P3.13.3d

  clearNotice: () => set({ lastUnloadNotice: null }),
  dismissCpuEta: async () => {
    try {
      await fetch('/api/system/sam3-cpu-eta/dismiss', {
        method: 'POST',
        headers: authHeaders(),
      });
    } catch {
      /* ignore */
    }
    set({ cpuEtaShow: false, cpuEtaRu: '' });
  },
  setPersistEnabled: (persistEnabled) => set({ persistEnabled }),
  setFullVideoEnabled: (fullVideoEnabled) => set({ fullVideoEnabled }),  // P3.13.3d: P1
  setTextPrompt: (textPrompt) => set({ textPrompt }),
  setLastPrompt: (lastPrompt) => set({ lastPrompt }),
  setTool: (tool) => set({ tool }),
  setHint: (hint) => set({ hint }),

  clearPropagate: () => {
    stopPropPoll();
    set({
      propTaskId: null,
      propStatus: 'idle',
      propProgress: 0,
      propProcessed: 0,
      propSampleTotal: 0,
      propMaskTotal: 0,
      propPersisted: 0,
      propMessage: '',
      propError: null,
      propFrames: [],
      propTotalWindows: 0,
      propCurrentWindow: 0,
    });
  },

  markUnloadedForBatch: () =>
    set({
      loaded: false,
      tool: 'none',
      hint: 'загрузите SAM3',
      lastUnloadNotice: 'SAM выгружен для запуска batch сегментации',
    }),

  markUnloadedByYolo: () =>
    set({
      loaded: false,
      tool: 'none',
      hint: get().ready ? 'загрузите SAM3' : 'нет sam3.pt',
      lastUnloadNotice: null,
    }),

  refreshStatus: async () => {
    try {
      const res = await fetch('/api/seg/sam3/status', { headers: authHeaders() });
      if (!res.ok) {
        set({ ready: false, loaded: false, weight: null });
        return;
      }
      const data = (await res.json()) as {
        ready?: boolean;
        loaded?: boolean;
        weight?: string | null;
        cpu_eta_show?: boolean;
        cpu_eta_ru?: string;
      };
      set({
        ready: Boolean(data.ready),
        loaded: Boolean(data.loaded),
        weight: data.weight ?? null,
        cpuEtaShow: Boolean(data.cpu_eta_show),
        cpuEtaRu: data.cpu_eta_ru || '',
        hint: data.loaded
          ? data.weight || 'sam3'
          : data.ready
            ? 'загрузите SAM3'
            : 'нет sam3.pt',
      });
    } catch {
      set({ ready: false, loaded: false });
    }
  },

  load: async () => {
    set({ busy: true });
    try {
      const res = await fetch('/api/seg/sam3/load', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({}),
      });
      const data = (await res.json().catch(() => ({}))) as {
        loaded?: boolean;
        weight?: string;
        detail?: string;
        yolo_seg_unloaded?: boolean;
      };
      if (!res.ok) {
        set({
          loaded: false,
          hint: typeof data.detail === 'string' ? data.detail : 'ошибка загрузки SAM3',
        });
        return { yoloSegUnloaded: false };
      }
      set({
        ready: true,
        loaded: true,
        weight: data.weight || 'sam3.pt',
        hint: data.weight || 'sam3',
        tool: 'point',
        lastUnloadNotice: data.yolo_seg_unloaded
          ? 'YOLO-seg выгружен для освобождения VRAM'
          : get().lastUnloadNotice,
      });
      return { yoloSegUnloaded: Boolean(data.yolo_seg_unloaded) };
    } finally {
      set({ busy: false });
    }
  },

  unload: async () => {
    try {
      await fetch('/api/seg/sam3/unload', { method: 'POST', headers: authHeaders() });
    } catch {
      /* ignore */
    }
    set({
      loaded: false,
      tool: 'none',
      hint: get().ready ? 'загрузите SAM3' : 'нет sam3.pt',
      lastPrompt: null,
    });
  },

  infer: async ({ imageBase64, points, bboxes, text }) => {
    set({ busy: true });
    try {
      const texts = text?.length ? text : undefined;
      const prompt: Sam3Prompt = texts?.length
        ? { text: texts }
        : {
            points: points?.length ? points : undefined,
            bboxes: bboxes?.length ? bboxes : undefined,
          };
      set({ lastPrompt: prompt });
      const res = await fetch('/api/seg/sam3/infer', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          image_base64: imageBase64,
          points: texts?.length ? [] : points || [],
          bboxes: texts?.length ? [] : bboxes || [],
          text: texts || [],
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        masks?: Sam3Mask[];
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`);
      }
      return Array.isArray(data.masks) ? data.masks : [];
    } finally {
      set({ busy: false });
    }
  },

  startPropagate: async ({ videoPath, timeSec, maxFrames = 30, persist, fullVideo }) => {
    const prompt = get().lastPrompt;
    const hasVisual = Boolean(prompt?.points?.length || prompt?.bboxes?.length);
    const hasText = Boolean(prompt?.text?.length);
    if (hasVisual === hasText) {
      set({
        propStatus: 'error',
        propError: 'Нет seed (точка/bbox или текст)',
      });
      return;
    }
    stopPropPoll();
    const usePersist = persist ?? get().persistEnabled;
    const useFullVideo = fullVideo ?? get().fullVideoEnabled;  // P3.13.3d: P1
    set({
      propStatus: 'running',
      propProgress: 0,
      propProcessed: 0,
      propSampleTotal: maxFrames,
      propMaskTotal: 0,
      propPersisted: 0,
      propMessage: 'Запуск…',
      propError: null,
      propFrames: [],
      propTotalWindows: 0,
      propCurrentWindow: 0,
      busy: true,
    });
    try {
      const res = await fetch('/api/seg/sam3/propagate', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          video_path: videoPath,
          time_sec: timeSec,
          max_frames: maxFrames,
          points: hasVisual ? prompt?.points || [] : [],
          bboxes: hasVisual ? prompt?.bboxes || [] : [],
          text: hasText ? prompt?.text || [] : [],
          persist: usePersist,
          full_video: useFullVideo ?? false,  // P3.13.3d
        }),
      });
      const data = (await res.json().catch(() => ({}))) as PropApiState & {
        detail?: string;
      };
      if (!res.ok) {
        throw new Error(
          typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`,
        );
      }
      applyProp(set, data);
      const taskId = data.task_id;
      if (!taskId) return;

      propPoll = setInterval(() => {
        void (async () => {
          try {
            const poll = await fetch(`/api/seg/sam3/propagate/${taskId}`, {
              headers: authHeaders(),
            });
            const body = (await poll.json().catch(() => ({}))) as PropApiState & {
              detail?: string;
            };
            if (!poll.ok) {
              stopPropPoll();
              set({
                propStatus: 'error',
                propError:
                  typeof body.detail === 'string' ? body.detail : `HTTP ${poll.status}`,
                busy: false,
              });
              return;
            }
            applyProp(set, body);
            if (
              body.status === 'done' ||
              body.status === 'error' ||
              body.status === 'aborted'
            ) {
              set({ busy: false });
            }
          } catch (e) {
            stopPropPoll();
            set({
              propStatus: 'error',
              propError: e instanceof Error ? e.message : 'Ошибка опроса',
              busy: false,
            });
          }
        })();
      }, 800);
    } catch (e) {
      stopPropPoll();
      set({
        propStatus: 'error',
        propError: e instanceof Error ? e.message : 'Ошибка запуска',
        propMessage: '',
        busy: false,
      });
    }
  },

  abortPropagate: async () => {
    const taskId = get().propTaskId;
    if (!taskId) return;
    try {
      const res = await fetch(`/api/seg/sam3/propagate/${taskId}/abort`, {
        method: 'POST',
        headers: authHeaders(),
      });
      const data = (await res.json().catch(() => ({}))) as PropApiState & {
        detail?: string;
      };
      if (!res.ok) {
        set({
          propError: typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`,
        });
        return;
      }
      applyProp(set, data);
      set({ busy: false });
    } catch (e) {
      set({
        propError: e instanceof Error ? e.message : 'Ошибка отмены',
        busy: false,
      });
    }
  },
}));
