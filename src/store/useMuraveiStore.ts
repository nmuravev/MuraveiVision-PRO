import { create } from 'zustand';
import {
  ViewMode,
  UiTheme,
  UserRole,
  DetectedObject,
  DetectionMoment,
  HardwareSpecs,
  AnalysisConfig,
  PersistedDetection,
  ClassCatalogItem,
  BoundingBox,
} from '../types/muravei';
import { classLabelRu } from '../lib/classLabels';
import { mediaPathsMatch } from '../lib/mediaPaths';

export function authHeaders(): HeadersInit {
  const token = localStorage.getItem('muravei-token');
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export function authToken(): string {
  return localStorage.getItem('muravei-token') || '';
}

export function detectionCropSrc(id: string, cropPath?: string | null): string {
  const token = encodeURIComponent(authToken());
  if (cropPath) {
    return `/api/media/stream?path=${encodeURIComponent(cropPath)}&token=${token}`;
  }
  return `/api/detections/${id}/crop?token=${token}`;
}

export function xyxyFromRow(row: PersistedDetection): BoundingBox {
  return {
    x1: row.bbox_x,
    y1: row.bbox_y,
    x2: row.bbox_x + row.bbox_w,
    y2: row.bbox_y + row.bbox_h,
  };
}

export const TIME_EPS = 0.35;
export const IOU_MATCH = 0.45;

export function boxIou(a: BoundingBox, b: BoundingBox): number {
  const ax1 = Math.min(a.x1, a.x2);
  const ay1 = Math.min(a.y1, a.y2);
  const ax2 = Math.max(a.x1, a.x2);
  const ay2 = Math.max(a.y1, a.y2);
  const bx1 = Math.min(b.x1, b.x2);
  const by1 = Math.min(b.y1, b.y2);
  const bx2 = Math.max(b.x1, b.x2);
  const by2 = Math.max(b.y1, b.y2);
  const ix1 = Math.max(ax1, bx1);
  const iy1 = Math.max(ay1, by1);
  const ix2 = Math.min(ax2, bx2);
  const iy2 = Math.min(ay2, by2);
  const inter = Math.max(0, ix2 - ix1) * Math.max(0, iy2 - iy1);
  const union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter;
  return union > 0 ? inter / union : 0;
}

export function matchesMemory(
  obj: DetectedObject,
  rows: PersistedDetection[],
  sourceVideo: string,
  timeSec: number,
): PersistedDetection | undefined {
  return rows.find((row) => {
    if (!mediaPathsMatch(row.source_video, sourceVideo)) return false;
    if (Math.abs(row.time_sec - timeSec) > TIME_EPS) return false;
    return boxIou(obj.bbox, xyxyFromRow(row)) >= IOU_MATCH;
  });
}

export function toDetectedObject(
  row: PersistedDetection,
  catalog: ClassCatalogItem[] = [],
): DetectedObject {
  const aiRaw = row.ai_class_name || row.class_name;
  return {
    id: row.id,
    class_en: row.class_name,
    class_ru: catalog.length ? classLabelRu(row.class_id, row.class_name, catalog) : row.class_name,
    ai_class_name: aiRaw !== row.class_name ? aiRaw : row.ai_class_name || undefined,
    class_id: row.class_id,
    confidence: row.confidence,
    bbox: xyxyFromRow(row),
    notes: row.user_notes,
    is_edited: row.is_edited,
    origin: row.origin === 'manual' ? 'manual' : 'auto',
    crop_path: row.crop_path || undefined,
    source_video: row.source_video,
    time_sec: row.time_sec,
  };
}

interface MuraveiState {
  currentView: ViewMode;
  uiTheme: UiTheme;
  userRole: UserRole | null;
  isAuthenticated: boolean;
  hardware: HardwareSpecs;
  analysisConfig: AnalysisConfig;
  moments: DetectionMoment[];
  activeDetection: DetectedObject | null;
  detections: PersistedDetection[];
  suppressedDetections: PersistedDetection[];
  /** Undo stack for patchDetection (v1: patch-only). Capped at 20. */
  undoStack: { id: string; prev: PersistedDetection }[];
  activeDetectionId: string | null;
  /** Last successfully hydrated source_video (scoped). */
  hydratedSourceVideo: string | null;
  classCatalog: ClassCatalogItem[];
  editMode: boolean;
  isStreaming: boolean;
  streamUrl: string | null;
  isRecording: boolean;
  recordingDuration: number;
  setCurrentView: (view: ViewMode) => void;
  setTheme: (theme: UiTheme) => void;
  setUserRole: (role: UserRole | null) => void;
  setAuthenticated: (auth: boolean) => void;
  setHardware: (specs: HardwareSpecs) => void;
  setAnalysisConfig: (config: Partial<AnalysisConfig>) => void;
  addMoment: (moment: DetectionMoment) => void;
  removeMoment: (id: string) => void;
  setMoments: (moments: DetectionMoment[]) => void;
  setActiveDetection: (detection: DetectedObject | null) => void;
  setActiveDetectionId: (id: string | null) => void;
  setEditMode: (edit: boolean) => void;
  clearDetections: () => void;
  hydrateDetections: (sourceVideo?: string | null) => Promise<void>;
  deleteAllForSource: (sourceVideo: string) => Promise<number>;
  loadClassCatalog: () => Promise<void>;
  patchDetection: (id: string, fields: Record<string, unknown>, frameJpeg?: string) => Promise<void>;
  undoLastEdit: () => Promise<void>;
  createDetection: (body: Record<string, unknown>) => Promise<PersistedDetection | null>;
  commitFrame: (body: Record<string, unknown>) => Promise<PersistedDetection[]>;
  deleteDetection: (id: string) => Promise<void>;
  dismissDetection: (obj: DetectedObject, sourceVideo: string, timeSec: number) => Promise<void>;
  setStreaming: (streaming: boolean) => void;
  setStreamUrl: (url: string | null) => void;
  setRecording: (recording: boolean) => void;
  setRecordingDuration: (duration: number) => void;
  resetSession: () => void;
}

const defaultHardware: HardwareSpecs = {
  cpu: 'Unknown',
  gpu: 'Unknown',
  vramMb: 0,
  cudaAvailable: false,
  providers: [],
  activeModel: 'best.pt',
};

const defaultAnalysisConfig: AnalysisConfig = {
  droneMode: false,
  frameStep: 15,
  confidenceThreshold: 0.20,
  modelName: 'best.pt',
  useFinetuned: true,
  aiAnalystEnabled: false,
};

function mergeRow(list: PersistedDetection[], row: PersistedDetection): PersistedDetection[] {
  const idx = list.findIndex((d) => d.id === row.id);
  if (row.is_deleted) return list.filter((d) => d.id !== row.id);
  if (idx === -1) return [...list, row];
  const next = list.slice();
  next[idx] = row;
  return next;
}

/** Module-level — do NOT put AbortController in Zustand state (re-renders). */
let hydrateAbort: AbortController | null = null;

export const useMuraveiStore = create<MuraveiState>((set, get) => ({
  currentView: 'mini',
  uiTheme: 'premiere',
  userRole: null,
  isAuthenticated: false,
  hardware: defaultHardware,
  analysisConfig: defaultAnalysisConfig,
  moments: [],
  activeDetection: null,
  detections: [],
  suppressedDetections: [],
  undoStack: [],
  activeDetectionId: null,
  hydratedSourceVideo: null,
  classCatalog: [],
  editMode: false,
  isStreaming: false,
  streamUrl: null,
  isRecording: false,
  recordingDuration: 0,

  setCurrentView: (view) => set({ currentView: view }),
  setTheme: (theme) => set({ uiTheme: theme }),
  setUserRole: (role) => set({ userRole: role }),
  setAuthenticated: (auth) => set({ isAuthenticated: auth }),
  setHardware: (specs) => set({ hardware: specs }),
  setAnalysisConfig: (config) =>
    set((state) => ({
      analysisConfig: { ...state.analysisConfig, ...config },
    })),
  addMoment: (moment) =>
    set((state) => ({
      moments: [...state.moments, moment],
    })),
  removeMoment: (id) =>
    set((state) => ({
      moments: state.moments.filter((m) => m.id !== id),
    })),
  setMoments: (moments) => set({ moments }),
  setActiveDetection: (detection) =>
    set({
      activeDetection: detection,
      activeDetectionId: detection?.id ?? null,
    }),
  setActiveDetectionId: (id) => {
    const row = get().detections.find((d) => d.id === id);
    set({
      activeDetectionId: id,
      activeDetection: row ? toDetectedObject(row) : get().activeDetection,
    });
  },
  setEditMode: (edit) => set({ editMode: edit }),

  clearDetections: () => {
    console.log('[Store] clearDetections');
    if (hydrateAbort) {
      hydrateAbort.abort();
      hydrateAbort = null;
    }
    set({
      detections: [],
      suppressedDetections: [],
      hydratedSourceVideo: null,
      activeDetection: null,
      activeDetectionId: null,
    });
  },

  hydrateDetections: async (sourceVideo) => {
    const prevHydrated = get().hydratedSourceVideo;
    console.log('[Store] hydrateDetections:', { sourceVideo, previous: prevHydrated });

    if (hydrateAbort) {
      hydrateAbort.abort();
      hydrateAbort = null;
    }

    const path = (sourceVideo || '').trim();
    if (!path) {
      console.log('[Store] clearDetections (no sourceVideo)');
      set({
        detections: [],
        suppressedDetections: [],
        hydratedSourceVideo: null,
      });
      return;
    }

    const ac = new AbortController();
    hydrateAbort = ac;
    const signal = ac.signal;

    try {
      const params = new URLSearchParams();
      params.set('source_video', path);
      params.set('include_deleted', 'true');
      const res = await fetch(`/api/detections?${params.toString()}`, {
        headers: authHeaders(),
        signal,
      });
      if (signal.aborted) return;
      if (!res.ok) return;
      const data = await res.json();
      if (signal.aborted) return;

      let rows = (data.detections ?? []) as PersistedDetection[];
      const needsGps = rows.some(
        (d) => !d.is_deleted && (d.gps_lat == null || d.gps_lon == null),
      );
      if (needsGps) {
        try {
          const geoRes = await fetch('/api/geo/import', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ video_path: path }),
            signal,
          });
          if (signal.aborted) return;
          if (geoRes.ok) {
            const geo = (await geoRes.json().catch(() => ({}))) as { backfilled?: number };
            if ((geo.backfilled ?? 0) > 0) {
              const res2 = await fetch(`/api/detections?${params.toString()}`, {
                headers: authHeaders(),
                signal,
              });
              if (signal.aborted) return;
              if (res2.ok) {
                const data2 = await res2.json();
                rows = (data2.detections ?? rows) as PersistedDetection[];
              }
            }
          }
        } catch (geoErr) {
          if ((geoErr as Error).name === 'AbortError') return;
        }
      }
      const live = rows.filter((d) => !d.is_deleted);
      const serverSuppressed = rows.filter((d) => d.is_deleted);
      // Preserve in-memory live-dismiss stubs for this source across remounts
      const clientStubs = get().suppressedDetections.filter(
        (d) =>
          d.is_deleted &&
          mediaPathsMatch(d.source_video || '', path) &&
          !serverSuppressed.some((s) => s.id === d.id),
      );
      const suppressed = [...serverSuppressed, ...clientStubs];
      const activeId = get().activeDetectionId;
      const activeRow = live.find((d) => d.id === activeId);
      console.log('[Store] loaded detections:', { sourceVideo: path, count: live.length });
      set({
        detections: live,
        suppressedDetections: suppressed,
        hydratedSourceVideo: path,
        activeDetection: activeRow ? toDetectedObject(activeRow) : get().activeDetection,
      });
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      console.error('[Store] hydrateDetections failed', e);
    } finally {
      if (hydrateAbort === ac) hydrateAbort = null;
    }
  },

  deleteAllForSource: async (sourceVideo) => {
    const path = (sourceVideo || '').trim();
    if (!path) return 0;
    const params = new URLSearchParams();
    params.set('source_video', path);
    params.set('all', 'true');
    const res = await fetch(`/api/detections?${params.toString()}`, {
      method: 'DELETE',
      headers: authHeaders(),
    });
    if (!res.ok) return 0;
    const data = (await res.json().catch(() => ({}))) as { deleted?: number };
    await get().hydrateDetections(path);
    return typeof data.deleted === 'number' ? data.deleted : 0;
  },

  loadClassCatalog: async () => {
    const res = await fetch('/api/detections/classes', { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    set({ classCatalog: data.classes ?? [] });
  },

  patchDetection: async (id, fields, frameJpeg) => {
    const prev = get().detections;
    const current = prev.find((d) => d.id === id);
    // Record undo snapshot (v1: patch-only). Skip recording when undoing.
    if (current && !fields.__undo) {
      const stack = [...get().undoStack, { id, prev: { ...current } }].slice(-20);
      set({ undoStack: stack });
    }
    if (current) {
      const { bbox, __undo: _undoFlag, ...rest } = fields;
      const optimistic: PersistedDetection = {
        ...current,
        is_edited: true,
        ...(rest as Partial<PersistedDetection>),
      };
      if (bbox && typeof bbox === 'object' && 'x1' in (bbox as BoundingBox)) {
        const b = bbox as BoundingBox;
        const x1 = Math.min(b.x1, b.x2);
        const y1 = Math.min(b.y1, b.y2);
        const x2 = Math.max(b.x1, b.x2);
        const y2 = Math.max(b.y1, b.y2);
        optimistic.bbox_x = x1;
        optimistic.bbox_y = y1;
        optimistic.bbox_w = Math.max(0.01, x2 - x1);
        optimistic.bbox_h = Math.max(0.01, y2 - y1);
      }
      set({
        detections: mergeRow(prev, optimistic),
        activeDetection: toDetectedObject(optimistic),
        activeDetectionId: id,
      });
    }
    try {
      const { __undo: _u, ...fieldBody } = fields;
      const body: Record<string, unknown> = { ...fieldBody };
      if (frameJpeg) body.frame_jpeg = frameJpeg;
      const res = await fetch(`/api/detections/${id}`, {
        method: 'PATCH',
        headers: authHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error('patch failed');
      const row = (await res.json()) as PersistedDetection;
      set((s) => ({
        detections: mergeRow(s.detections, row),
        activeDetection: toDetectedObject(row),
        activeDetectionId: row.id,
      }));
    } catch {
      set({ detections: prev });
    }
  },

  undoLastEdit: async () => {
    const stack = get().undoStack;
    if (!stack.length) return;
    const entry = stack[stack.length - 1];
    const prev = entry.prev;
    // Rebuild patchable fields from the pre-edit snapshot.
    const restoreFields: Record<string, unknown> = {
      class_id: prev.class_id,
      class_name: prev.class_name,
      confidence: prev.confidence,
      user_notes: prev.user_notes,
      bbox: {
        x1: prev.bbox_x,
        y1: prev.bbox_y,
        x2: prev.bbox_x + prev.bbox_w,
        y2: prev.bbox_y + prev.bbox_h,
      },
      __undo: true, // signals patchDetection not to push a new undo entry
    };
    set({ undoStack: stack.slice(0, -1) });
    await get().patchDetection(entry.id, restoreFields);
  },

  createDetection: async (body) => {
    const bbox = body.bbox as BoundingBox | undefined;
    const tempId = typeof body.id === 'string' ? body.id : crypto.randomUUID();
    const prev = get().detections;
    const optimistic: PersistedDetection = {
      id: tempId,
      created_at: Date.now() / 1000,
      source_video: String(body.source_video ?? 'local'),
      time_sec: Number(body.time_sec ?? 0),
      frame_idx: Number(body.frame_idx ?? 0),
      class_id: Number(body.class_id ?? 0),
      class_name: String(body.class_name ?? 'class_0'),
      confidence: Number(body.confidence ?? 1),
      bbox_x: bbox?.x1 ?? 0,
      bbox_y: bbox?.y1 ?? 0,
      bbox_w: bbox ? Math.max(0.01, bbox.x2 - bbox.x1) : 0.1,
      bbox_h: bbox ? Math.max(0.01, bbox.y2 - bbox.y1) : 0.1,
      crop_path: null,
      is_edited: true,
      user_notes: String(body.user_notes ?? ''),
      is_deleted: false,
      origin: 'manual',
    };
    set({
      detections: mergeRow(prev, optimistic),
      activeDetection: toDetectedObject(optimistic),
      activeDetectionId: tempId,
    });
    try {
      const res = await fetch('/api/detections', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ ...body, id: tempId }),
      });
      if (!res.ok) throw new Error('create failed');
      const row = (await res.json()) as PersistedDetection;
      set((s) => ({
        detections: mergeRow(s.detections, row),
        activeDetection: toDetectedObject(row),
        activeDetectionId: row.id,
      }));
      return row;
    } catch {
      set({ detections: prev });
      return null;
    }
  },

  commitFrame: async (body) => {
    const res = await fetch('/api/detections/commit', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(body),
    });
    if (!res.ok) return [];
    const data = await res.json();
    const rows = (data.detections ?? []) as PersistedDetection[];
    set((s) => {
      let next = s.detections;
      for (const row of rows) next = mergeRow(next, row);
      const first = rows[0];
      return {
        detections: next,
        activeDetection: first ? toDetectedObject(first) : s.activeDetection,
        activeDetectionId: first ? first.id : s.activeDetectionId,
      };
    });
    return rows;
  },

  deleteDetection: async (id) => {
    const prev = get().detections;
    const prevSuppressed = get().suppressedDetections;
    const row = prev.find((d) => d.id === id);
    const wasActive = get().activeDetectionId === id;
    set({
      detections: prev.filter((d) => d.id !== id),
      suppressedDetections: row
        ? [...prevSuppressed, { ...row, is_deleted: true }]
        : prevSuppressed,
      activeDetection: wasActive ? null : get().activeDetection,
      activeDetectionId: wasActive ? null : get().activeDetectionId,
    });
    try {
      const res = await fetch(`/api/detections/${id}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error('delete failed');
    } catch {
      set({ detections: prev, suppressedDetections: prevSuppressed });
    }
  },

  dismissDetection: async (obj, sourceVideo, timeSec) => {
    const persisted = get().detections.find((d) => d.id === obj.id);
    if (persisted) {
      await get().deleteDetection(persisted.id);
      return;
    }
    const stub: PersistedDetection = {
      id: obj.id,
      created_at: Date.now() / 1000,
      source_video: sourceVideo,
      time_sec: obj.time_sec ?? timeSec,
      frame_idx: 0,
      class_id: obj.class_id ?? -1,
      class_name: obj.class_en || obj.class_ru,
      confidence: obj.confidence,
      bbox_x: obj.bbox.x1,
      bbox_y: obj.bbox.y1,
      bbox_w: Math.max(0.01, obj.bbox.x2 - obj.bbox.x1),
      bbox_h: Math.max(0.01, obj.bbox.y2 - obj.bbox.y1),
      crop_path: null,
      is_edited: false,
      user_notes: '',
      is_deleted: true,
      origin: obj.origin ?? 'auto',
    };
    set({
      suppressedDetections: [...get().suppressedDetections, stub],
      activeDetection: get().activeDetectionId === obj.id ? null : get().activeDetection,
      activeDetectionId: get().activeDetectionId === obj.id ? null : get().activeDetectionId,
    });
  },

  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setStreamUrl: (url) => set({ streamUrl: url }),
  setRecording: (recording) => set({ isRecording: recording }),
  setRecordingDuration: (duration) => set({ recordingDuration: duration }),
  resetSession: () =>
    set({
      currentView: 'mini',
      moments: [],
      detections: [],
      suppressedDetections: [],
      hydratedSourceVideo: null,
      activeDetection: null,
      activeDetectionId: null,
      editMode: false,
      isStreaming: false,
      streamUrl: null,
      isRecording: false,
      recordingDuration: 0,
      undoStack: [],
    }),
}));
