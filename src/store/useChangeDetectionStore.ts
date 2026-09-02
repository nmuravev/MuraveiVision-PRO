import { create } from 'zustand';
import { authHeaders } from './useMuraveiStore';
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
  } | null;
};

interface ChangeDetectionState {
  result: ChangeDetectionResult | null;
  loading: boolean;
  error: string | null;
  activeHighlight: ChangeHighlight | null;
  runAnalysis: (params: {
    videoBefore: string;
    videoAfter: string;
    timeBefore: number;
    timeAfter: number;
    timeWindowSec: number;
  }) => Promise<void>;
  setActiveHighlight: (h: ChangeHighlight | null) => void;
  clear: () => void;
}

export const useChangeDetectionStore = create<ChangeDetectionState>((set) => ({
  result: null,
  loading: false,
  error: null,
  activeHighlight: null,

  clear: () => set({ result: null, loading: false, error: null, activeHighlight: null }),

  setActiveHighlight: (activeHighlight) => set({ activeHighlight }),

  runAnalysis: async ({
    videoBefore,
    videoAfter,
    timeBefore,
    timeAfter,
    timeWindowSec,
  }) => {
    set({ loading: true, error: null });
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
      set({ result, loading: false, error: null, activeHighlight: null });
    } catch (e) {
      set({
        loading: false,
        error: e instanceof Error ? e.message : 'Ошибка анализа',
        result: null,
      });
    }
  },
}));
