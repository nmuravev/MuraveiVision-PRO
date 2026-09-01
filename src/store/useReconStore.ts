import { create } from 'zustand';

export type ReconManifest = {
  job_id: string;
  video_path: string;
  t_start: number;
  t_end: number;
  status: string;
  artifact?: string | null;
  poses_file?: string;
  sparse_file?: string;
  scale_m_per_unit?: number | null;
  scale_reference?: {
    point_a?: number[];
    point_b?: number[];
    distance_m?: number;
    scale_direction?: number[];
  } | null;
  rotation_x?: number;
};

export type RaycastMarker = {
  id: string;
  detectionId: string;
  position: [number, number, number];
  className: string;
  aiClassName?: string;
  distanceM: number | null;
  azimuthDeg: number | null;
};

export type RaycastRequest = {
  detectionId: string;
  timeSec: number;
  u: number;
  v: number;
  className: string;
  aiClassName?: string;
};

type ReconState = {
  viewMode: 'geo' | 'scene';
  manifest: ReconManifest | null;
  reconMessage: string;
  reconProgress: number;
  reconRunning: boolean;
  sparsePoints: Float32Array | null;
  raycastMarkers: RaycastMarker[];
  pendingRaycast: RaycastRequest | null;
  toast: string | null;
  setViewMode: (m: 'geo' | 'scene') => void;
  setManifest: (m: ReconManifest | null) => void;
  setReconProgress: (msg: string, progress: number, running: boolean) => void;
  setSparsePoints: (pts: Float32Array | null) => void;
  requestRaycast: (req: RaycastRequest) => void;
  clearPendingRaycast: () => void;
  addRaycastMarker: (m: RaycastMarker) => void;
  setToast: (t: string | null) => void;
};

export const useReconStore = create<ReconState>((set) => ({
  viewMode: 'geo',
  manifest: null,
  reconMessage: '',
  reconProgress: 0,
  reconRunning: false,
  sparsePoints: null,
  raycastMarkers: [],
  pendingRaycast: null,
  toast: null,
  setViewMode: (m) => set({ viewMode: m }),
  setManifest: (manifest) =>
    set((state) => {
      const changedJob = state.manifest?.job_id !== manifest?.job_id;
      return {
        manifest,
        ...(changedJob ? { raycastMarkers: [], pendingRaycast: null, toast: null } : {}),
      };
    }),
  setReconProgress: (reconMessage, reconProgress, reconRunning) =>
    set({ reconMessage, reconProgress, reconRunning }),
  setSparsePoints: (sparsePoints) => set({ sparsePoints }),
  requestRaycast: (pendingRaycast) => set({ pendingRaycast }),
  clearPendingRaycast: () => set({ pendingRaycast: null }),
  addRaycastMarker: (marker) =>
    set((s) => ({ raycastMarkers: [...s.raycastMarkers, marker] })),
  setToast: (toast) => set({ toast }),
}));
