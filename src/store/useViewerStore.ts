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
  isPlaying: false,
});

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
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          sourcePath: path,
          sourceUrl: url,
          sourceMode: 'archive',
          liveActive: false,
        },
      },
      focusedViewerId: viewerId,
    })),
  setSourceMode: (viewerId, mode) =>
    set((s) => ({
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          sourceMode: mode,
        },
      },
    })),
  setLiveUrl: (viewerId, url) =>
    set((s) => ({
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          liveUrl: url,
        },
      },
    })),
  setLiveActive: (viewerId, active) =>
    set((s) => ({
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          liveActive: active,
          sourceMode: active ? 'live' : s.viewers[viewerId]?.sourceMode ?? 'archive',
        },
      },
    })),
  setYoloEnabled: (viewerId, enabled) =>
    set((s) => ({
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          yoloEnabled: enabled,
        },
      },
    })),
  setPlaying: (viewerId, playing) =>
    set((s) => ({
      viewers: {
        ...s.viewers,
        [viewerId]: {
          ...(s.viewers[viewerId] ?? defaultViewer()),
          isPlaying: playing,
        },
      },
    })),
  setShowMotion: (on) => set({ showMotion: on }),
  setCompareMode: (on) => set({ compareMode: on }),
  setSyncPlayhead: (on) => set({ syncPlayhead: on }),
  setLastObjects: (viewerId, objects) =>
    set((s) => ({
      lastObjects: { ...s.lastObjects, [viewerId]: objects },
    })),
}));
