import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';

export type Sam3Tool = 'none' | 'point';

export type Sam3Mask = {
  class: string;
  conf: number;
  polygon_norm: number[][];
};

interface Sam3State {
  ready: boolean;
  loaded: boolean;
  weight: string | null;
  busy: boolean;
  tool: Sam3Tool;
  hint: string;
  lastUnloadNotice: string | null;
  refreshStatus: () => Promise<void>;
  load: () => Promise<{ yoloSegUnloaded: boolean }>;
  unload: () => Promise<void>;
  setTool: (t: Sam3Tool) => void;
  clearNotice: () => void;
  markUnloadedForBatch: () => void;
  markUnloadedByYolo: () => void;
  infer: (params: {
    imageBase64: string;
    points?: { x: number; y: number; label: number }[];
    bboxes?: { x1: number; y1: number; x2: number; y2: number }[];
  }) => Promise<Sam3Mask[]>;
}

export const useSam3Store = create<Sam3State>((set, get) => ({
  ready: false,
  loaded: false,
  weight: null,
  busy: false,
  tool: 'none',
  hint: '',
  lastUnloadNotice: null,

  clearNotice: () => set({ lastUnloadNotice: null }),

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

  setTool: (tool) => set({ tool }),

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
      };
      set({
        ready: Boolean(data.ready),
        loaded: Boolean(data.loaded),
        weight: data.weight ?? null,
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
    });
  },

  infer: async ({ imageBase64, points, bboxes }) => {
    set({ busy: true });
    try {
      const res = await fetch('/api/seg/sam3/infer', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          image_base64: imageBase64,
          points: points || [],
          bboxes: bboxes || [],
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
}));
