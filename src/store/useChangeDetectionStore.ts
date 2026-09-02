import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
import { downloadAuthorized } from '../lib/download';
import type { BoundingBox } from '../types/muravei';

export type ChangeType = 'new' | 'removed' | 'moved';

export type ChangeHighlight = {
  kind: ChangeType;
  id: string;
};

export type ChangeSummary = {
  total_before: number;
  total_after: number;
  matched: number;
  stable: number;
  moved: number;
  new: number;
  removed: number;
};

export type ChangeMatch = {
  before_id: string;
  after_id: string;
  class_name: string;
  distance_m: number;
  status: 'stable' | 'moved';
  before_bbox: BoundingBox;
  after_bbox: BoundingBox;
};

export type ChangeItem = {
  id: string;
  class_name: string;
  bbox: BoundingBox;
  confidence?: number;
  gps_lat?: number;
  gps_lon?: number;
};

export type ChangeDetectionResult = {
  method: 'gps' | 'image' | 'hybrid' | 'none';
  aligned: boolean;
  message: string | null;
  summary: ChangeSummary;
  matches: ChangeMatch[];
  new: ChangeItem[];
  removed: ChangeItem[];
  image_diff: {
    inlier_ratio: number;
    regions: { kind: string; bbox: BoundingBox }[];
    heatmap_b64?: string | null;
  } | null;
};

export type SyncSource = 'auto' | 'tracks' | 'detections';

export type SyncPair = {
  time_before: number;
  time_after: number;
  distance_m?: number | null;
  class_name?: string;
  conf?: number;
  lat?: number;
  lon?: number;
};

export type SyncSegment = {
  start_before: number;
  end_before: number;
  start_after: number;
  end_after: number;
  pair_count: number;
};

export type SyncReport = {
  method_used: 'gps' | 'detections' | 'none';
  pairs: SyncPair[];
  segments: SyncSegment[];
  message: string | null;
  pair_count_total: number;
};

export type CompareSeekTargets = {
  'viewer-1': number;
  'viewer-2': number;
  epoch: number;
};

export type LastAnalyzeParams = {
  videoBefore: string;
  videoAfter: string;
  timeBefore: number;
  timeAfter: number;
  timeWindowSec: number;
};

interface ChangeDetectionState {
  result: ChangeDetectionResult | null;
  loading: boolean;
  error: string | null;
  activeHighlight: ChangeHighlight | null;
  syncResult: SyncReport | null;
  syncLoading: boolean;
  syncError: string | null;
  seekTargets: CompareSeekTargets | null;
  lastAnalyze: LastAnalyzeParams | null;
  exportBusy: boolean;
  exportError: string | null;
  showHeatmap: boolean;
  setShowHeatmap: (v: boolean) => void;
  runAnalysis: (params: LastAnalyzeParams) => Promise<void>;
  applyPairResult: (
    result: ChangeDetectionResult,
    params: LastAnalyzeParams,
  ) => void;
  runSync: (params: {
    videoBefore: string;
    videoAfter: string;
    source: SyncSource;
  }) => Promise<void>;
  exportReport: (format: 'html' | 'kml') => Promise<void>;
  requestSeek: (timeBefore: number, timeAfter: number) => void;
  setActiveHighlight: (h: ChangeHighlight | null) => void;
  clear: () => void;
}

export const useChangeDetectionStore = create<ChangeDetectionState>((set, get) => ({
  result: null,
  loading: false,
  error: null,
  activeHighlight: null,
  syncResult: null,
  syncLoading: false,
  syncError: null,
  seekTargets: null,
  lastAnalyze: null,
  exportBusy: false,
  exportError: null,
  showHeatmap: false,

  clear: () =>
    set({
      result: null,
      loading: false,
      error: null,
      activeHighlight: null,
      syncResult: null,
      syncLoading: false,
      syncError: null,
      seekTargets: null,
      lastAnalyze: null,
      exportBusy: false,
      exportError: null,
      showHeatmap: false,
    }),

  setShowHeatmap: (showHeatmap) => set({ showHeatmap }),

  setActiveHighlight: (activeHighlight) => set({ activeHighlight }),

  requestSeek: (timeBefore, timeAfter) =>
    set((s) => ({
      seekTargets: {
        'viewer-1': timeBefore,
        'viewer-2': timeAfter,
        epoch: (s.seekTargets?.epoch ?? 0) + 1,
      },
    })),

  applyPairResult: (result, params) =>
    set({
      result,
      loading: false,
      error: null,
      activeHighlight: null,
      showHeatmap: false,
      lastAnalyze: params,
      exportError: null,
    }),

  runAnalysis: async ({
    videoBefore,
    videoAfter,
    timeBefore,
    timeAfter,
    timeWindowSec,
  }) => {
    set({ loading: true, error: null, exportError: null, showHeatmap: false });
    try {
      const res = await fetch('/api/change-detection/analyze', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          video_before: videoBefore,
          video_after: videoAfter,
          time_before: timeBefore,
          time_after: timeAfter,
          time_window_sec: timeWindowSec,
          use_gps: true,
          use_image_fallback: true,
        }),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const result = (await res.json()) as ChangeDetectionResult;
      set({
        result,
        loading: false,
        error: null,
        activeHighlight: null,
        showHeatmap: false,
        lastAnalyze: {
          videoBefore,
          videoAfter,
          timeBefore,
          timeAfter,
          timeWindowSec,
        },
      });
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : 'Ошибка анализа',
        result: null,
        showHeatmap: false,
      });
    }
  },

  runSync: async ({ videoBefore, videoAfter, source }) => {
    set({ syncLoading: true, syncError: null });
    try {
      const res = await fetch('/api/change-detection/sync', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          video_before: videoBefore,
          video_after: videoAfter,
          source,
          tolerance_m: 15.0,
        }),
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(
          typeof err.detail === 'string' ? err.detail : `HTTP ${res.status}`,
        );
      }
      const syncResult = (await res.json()) as SyncReport;
      set({ syncResult, syncLoading: false, syncError: null });
    } catch (e) {
      set({
        syncLoading: false,
        syncError: e instanceof Error ? e.message : 'Ошибка синхронизации',
        syncResult: null,
      });
    }
  },

  exportReport: async (format) => {
    const params = get().lastAnalyze;
    if (!params) {
      set({ exportError: 'Нет параметров анализа для экспорта' });
      return;
    }
    set({ exportBusy: true, exportError: null });
    try {
      const qs = new URLSearchParams({
        format,
        video_before: params.videoBefore,
        video_after: params.videoAfter,
        time_before: String(params.timeBefore),
        time_after: String(params.timeAfter),
        time_window_sec: String(params.timeWindowSec),
      });
      await downloadAuthorized(`/api/change-detection/export?${qs.toString()}`, {
        filename:
          format === 'html'
            ? 'muravei_change_report.html'
            : 'muravei_change_report.kml',
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
