import { create } from 'zustand';
import type { DetectedObject } from '../types/muravei';

export type ViewerSourceMode = 'archive' | 'live';

export interface ViewerState {
  sourcePath: string | null;
  sourceUrl: string | null;
  sourceMode: ViewerSourceMode;
  liveUrl: string | null;
  liveActive: boolean;
  yoloEnabled: boolean;
  /** null = inherit System use_sahi_default; boolean overrides WS payload */
  useSahi: boolean | null;
  isPlaying: boolean;
}

interface ViewerStore {
  viewers: Record<string, ViewerState>;
  /** Which viewer drives Timeline / filmstrip (viewer-1 … viewer-4). */
  focusedViewerId: string;
  /** Sprint 3: draw motion arrows on overlay */
  showMotion: boolean;
  /** Sprint 3: было (viewer-1) / стало (viewer-2) delta strip */
  compareMode: boolean;
  /** Sync playhead seek across archive viewers when compare on */
  syncPlayhead: boolean;
  /** Last live detections per viewer for compare */
  lastObjects: Record<string, DetectedObject[]>;
  setFocusedViewer: (viewerId: string) => void;
  setSource: (viewerId: string, path: string | null, url?: string | null) => void;
  setSourceMode: (viewerId: string, mode: ViewerSourceMode) => void;
  setLiveUrl: (viewerId: string, url: string | null) => void;
  setLiveActive: (viewerId: string, active: boolean) => void;
  setYoloEnabled: (viewerId: string, enabled: boolean) => void;
  setUseSahi: (viewerId: string, useSahi: boolean | null) => void;
  setPlaying: (viewerId: string, playing: boolean) => void;
  setShowMotion: (on: boolean) => void;
  setCompareMode: (on: boolean) => void;
  setSyncPlayhead: (on: boolean) => void;
  setLastObjects: (viewerId: string, objects: DetectedObject[]) => void;
}

const defaultViewer = (): ViewerState => ({
  sourcePath: null,
  sourceUrl: null,
  sourceMode: 'archive',
  liveUrl: null,
  liveActive: false,
  yoloEnabled: true,
  useSahi: null,
  isPlaying: false,
});

/** Ensure a viewer slot exists before updating — returns a new viewers object. */
function ensureViewer(
  viewers: Record<string, ViewerState>,
  viewerId: string,
  patch: Partial<ViewerState>,
): Record<string, ViewerState> {
  const existing = viewers[viewerId];
  return {
    ...viewers,
    [viewerId]: {
      ...(existing ?? defaultViewer()),
      ...patch,
    },
  };
}

export const useViewerStore = create<ViewerStore>((set) => ({
  viewers: {
    'viewer-1': defaultViewer(),
    'viewer-2': defaultViewer(),
    'viewer-3': defaultViewer(),
    'viewer-4': defaultViewer(),
  },
  focusedViewerId: 'viewer-1',
  showMotion: true,
  compareMode: false,
  syncPlayhead: true,
  lastObjects: {},
  setFocusedViewer: (viewerId) => set({ focusedViewerId: viewerId }),
  setSource: (viewerId, path, url = null) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, {
        sourcePath: path,
        sourceUrl: url,
        sourceMode: 'archive',
        liveActive: false,
      }),
      focusedViewerId: viewerId,
    })),
  setSourceMode: (viewerId, mode) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, { sourceMode: mode }),
    })),
  setLiveUrl: (viewerId, url) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, { liveUrl: url }),
    })),
  setLiveActive: (viewerId, active) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, {
        liveActive: active,
        sourceMode: active ? 'live' : s.viewers[viewerId]?.sourceMode ?? 'archive',
      }),
    })),
  setYoloEnabled: (viewerId, enabled) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, { yoloEnabled: enabled }),
    })),
  setUseSahi: (viewerId, useSahi) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, { useSahi }),
    })),
  setPlaying: (viewerId, playing) =>
    set((s) => ({
      viewers: ensureViewer(s.viewers, viewerId, { isPlaying: playing }),
    })),
  setShowMotion: (on) => set({ showMotion: on }),
  setCompareMode: (on) => set({ compareMode: on }),
  setSyncPlayhead: (on) => set({ syncPlayhead: on }),
  setLastObjects: (viewerId, objects) =>
    set((s) => ({
      lastObjects: { ...s.lastObjects, [viewerId]: objects },
    })),
}));
