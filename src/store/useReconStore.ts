import { create } from 'zustand';

export type ReconManifest = {
  job_id: string;
  video_path: string;
  t_start: number;
  t_end: number;
  status: string;
  error?: string | null;
  artifact?: string | null;
  poses_file?: string;
  sparse_file?: string;
  scale_m_per_unit?: number | null;
  /** After Build3D sparse-only: prefer Balanced for photoreal splat */
  next_action?: string | null;
  scale_reference?: {
    point_a?: number[];
    point_b?: number[];
    distance_m?: number;
    scale_direction?: number[];
  } | null;
  rotation_x?: number;
  frame_count?: number;
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

export type ReconProgressMeta = {
  jobId?: string | null;
  stage?: string | null;
};

type ReconState = {
  viewMode: 'geo' | 'scene';
  manifest: ReconManifest | null;
  colmapAvailable: boolean;
  reconMessage: string;
  reconPhase: string | null;
  /** Fine-grained COLMAP stage from SSE (feature_extractor, mapper, …). */
  reconStage: string | null;
  reconProgress: number;
  reconRunning: boolean;
  /** Live job from status/SSE — not the last completed manifest job. */
  reconJobId: string | null;
  lastReconMessage: string;
  sparsePoints: Float32Array | null;
  sparseWeak: boolean;
  raycastMarkers: RaycastMarker[];
  pendingRaycast: RaycastRequest | null;
  toast: string | null;
  setViewMode: (m: 'geo' | 'scene') => void;
  setManifest: (m: ReconManifest | null, colmapAvailable?: boolean) => void;
  setReconProgress: (
    msg: string,
    progress: number,
    running: boolean,
    phase?: string | null,
    meta?: ReconProgressMeta,
  ) => void;
  setSparsePoints: (pts: Float32Array | null, weak?: boolean) => void;
  requestRaycast: (req: RaycastRequest) => void;
  clearPendingRaycast: () => void;
  addRaycastMarker: (m: RaycastMarker) => void;
  setToast: (t: string | null) => void;
};

export const useReconStore = create<ReconState>((set) => ({
  viewMode: 'geo',
  manifest: null,
  colmapAvailable: false,
  reconMessage: '',
  reconPhase: null,
  reconStage: null,
  reconProgress: 0,
  reconRunning: false,
  reconJobId: null,
  lastReconMessage: '',
  sparsePoints: null,
  sparseWeak: false,
  raycastMarkers: [],
  pendingRaycast: null,
  toast: null,
  setViewMode: (m) => set({ viewMode: m }),
  setManifest: (manifest, colmapAvailable) =>
    set((state) => {
      const changedJob = state.manifest?.job_id !== manifest?.job_id;
      return {
        manifest,
        colmapAvailable: colmapAvailable ?? state.colmapAvailable,
        ...(changedJob ? { raycastMarkers: [], pendingRaycast: null, toast: null } : {}),
      };
    }),
  setReconProgress: (reconMessage, reconProgress, reconRunning, reconPhase = null, meta) =>
    set((s) => ({
      reconMessage,
      reconProgress,
      reconRunning,
      reconPhase,
      reconJobId: meta && 'jobId' in meta ? meta.jobId ?? null : s.reconJobId,
      reconStage:
        meta && 'stage' in meta
          ? meta.stage ?? null
          : reconRunning
            ? s.reconStage
            : null,
      lastReconMessage: reconRunning ? s.lastReconMessage : reconMessage || s.lastReconMessage,
    })),
  setSparsePoints: (sparsePoints, sparseWeak = false) => set({ sparsePoints, sparseWeak }),
  requestRaycast: (pendingRaycast) => set({ pendingRaycast }),
  clearPendingRaycast: () => set({ pendingRaycast: null }),
  addRaycastMarker: (marker) =>
    set((s) => ({ raycastMarkers: [...s.raycastMarkers, marker] })),
  setToast: (toast) => set({ toast }),
}));
