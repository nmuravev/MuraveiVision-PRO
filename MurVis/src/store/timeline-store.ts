import { create } from "zustand";
import { persist, subscribeWithSelector } from "zustand/middleware";
import { yoloDebug } from "../debug/yoloDebug";

export const TIMELINE_WORKSPACE_STORAGE_KEY = "openreel-timeline-workspace";

export const ZOOM_PRESETS = {
  MIN: 10,
  DEFAULT: 50,
  MAX: 500,
} as const;

export type PlaybackState = "stopped" | "playing" | "paused";

/** Compare Sync: slave viewers follow primary seeks via seekEpoch. */
export type TimelineSyncMode = "off" | "follow";

export type AnalysisJob = {
  id: string;
  sourcePath: string;
  inPoint: number;
  outPoint: number;
};

export type LiveMark = {
  id: string;
  timestamp: number;
  class_en: string;
  class_ru: string;
  confidence: number;
  bucketKey: string;
};

export interface TimelineState {
  playheadPosition: number;
  playbackState: PlaybackState;
  playbackLockedReason: string | null;
  playbackRate: number;
  pixelsPerSecond: number;
  scrollX: number;
  scrollY: number;
  viewportWidth: number;
  viewportHeight: number;
  trackHeight: number;
  trackHeights: Record<string, number>;
  loopEnabled: boolean;
  loopStart: number;
  loopEnd: number;
  isScrubbing: boolean;
  scrubPosition: number | null;
  expandedTracks: string[];
  expandedClipKeyframes: string[];
  /** @deprecated Use expandedTracks array instead */
  _expandedTracksSet?: Set<string>;
  /** @deprecated Use expandedClipKeyframes array instead */
  _expandedClipKeyframesSet?: Set<string>;
  keyframeEditMode: boolean;
  mediaDuration: number;
  previewFrame: string | null;
  filmstrip: { t: number; image: string }[];
  filmstripPath: string | null;
  inPoint: number | null;
  outPoint: number | null;
  seekEpoch: number;
  /** When 'follow', non-primary archive viewers seek on seekEpoch (Compare Sync). */
  syncMode: TimelineSyncMode;
  /** Jump target after source change; Viewer consumes on metadata/restore, then clears. */
  pendingJump: number | null;
  analysisQueue: AnalysisJob[];
  liveMarks: LiveMark[];
  setMediaDuration: (duration: number) => void;
  setSyncMode: (mode: TimelineSyncMode) => void;
  setPendingJump: (timeSec: number | null) => void;
  setPreviewFrame: (dataUrl: string | null) => void;
  setFilmstrip: (path: string, frames: { t: number; image: string }[]) => void;
  markIn: (time?: number) => void;
  markOut: (time?: number) => void;
  clearInOut: () => void;
  enqueueRange: (sourcePath: string, range?: { inPoint: number; outPoint: number }) => boolean;
  removeQueued: (id: string) => void;
  updateQueued: (id: string, patch: { inPoint?: number; outPoint?: number }) => void;
  recordLiveHits: (hits: { id: string; class_en: string; class_ru?: string; confidence: number }[], timeSec: number) => void;
  clearLiveMarks: () => void;
  removeLiveMark: (id: string) => void;
  play: () => void;
  pause: () => void;
  stop: () => void;
  togglePlayback: () => void;
  lockPlayback: (reason?: string) => void;
  unlockPlayback: () => void;
  setPlaybackRate: (rate: number) => void;
  setPlayheadPosition: (position: number) => void;
  seekTo: (position: number) => void;
  seekRelative: (delta: number) => void;
  stepFrame: (deltaFrames: number) => void;
  seekToStart: () => void;
  seekToEnd: (duration: number) => void;
  startScrubbing: (position: number) => void;
  updateScrubPosition: (position: number) => void;
  endScrubbing: () => void;
  zoomIn: () => void;
  zoomOut: () => void;
  setZoom: (pixelsPerSecond: number) => void;
  zoomToFit: (duration: number) => void;
  resetZoom: () => void;
  setScrollX: (scrollX: number) => void;
  setScrollY: (scrollY: number) => void;
  scrollToPlayhead: () => void;
  setViewportDimensions: (width: number, height: number) => void;
  setTrackHeight: (height: number) => void;
  setTrackHeightById: (trackId: string, height: number) => void;
  getTrackHeight: (trackId: string, trackType?: string) => number;
  setLoopEnabled: (enabled: boolean) => void;
  setLoopRange: (start: number, end: number) => void;
  timeToPixels: (time: number) => number;
  pixelsToTime: (pixels: number) => number;
  getVisibleTimeRange: () => { start: number; end: number };
  isTimeVisible: (time: number) => boolean;
  toggleTrackExpanded: (trackId: string) => void;
  setTrackExpanded: (trackId: string, expanded: boolean) => void;
  isTrackExpanded: (trackId: string) => boolean;
  toggleClipKeyframesExpanded: (clipId: string) => void;
  setClipKeyframesExpanded: (clipId: string, expanded: boolean) => void;
  isClipKeyframesExpanded: (clipId: string) => boolean;
  setKeyframeEditMode: (enabled: boolean) => void;
}

export const useTimelineStore = create<TimelineState>()(
  subscribeWithSelector(
    persist(
      (set, get) => ({
    playheadPosition: 0,
    playbackState: "stopped",
    playbackLockedReason: null,
    playbackRate: 1.0,

    pixelsPerSecond: ZOOM_PRESETS.DEFAULT,
    scrollX: 0,
    scrollY: 0,

    viewportWidth: 800,
    viewportHeight: 400,
    trackHeight: 62,
    trackHeights: {},

    loopEnabled: false,
    loopStart: 0,
    loopEnd: 0,

    isScrubbing: false,
    scrubPosition: null,

    expandedTracks: [] as string[],
    expandedClipKeyframes: [] as string[],
    keyframeEditMode: false,

    mediaDuration: 0,
    previewFrame: null,
    filmstrip: [],
    filmstripPath: null,
    inPoint: null,
    outPoint: null,
    seekEpoch: 0,
    syncMode: "off",
    pendingJump: null,
    analysisQueue: [],
    liveMarks: [],

    setMediaDuration: (duration) => {
      const safe = Number.isFinite(duration) && duration > 0 ? duration : 0;
      set({ mediaDuration: safe });
    },

    setSyncMode: (mode) => {
      set({ syncMode: mode });
    },

    setPendingJump: (timeSec) => {
      set({ pendingJump: timeSec == null ? null : Math.max(0, timeSec) });
    },

    setPreviewFrame: (dataUrl) => {
      set({ previewFrame: dataUrl });
    },

    setFilmstrip: (path, frames) => {
      set({ filmstripPath: path, filmstrip: frames });
    },

    enqueueRange: (sourcePath, range) => {
      const store = get();
      const inPoint = range?.inPoint ?? store.inPoint;
      const outPoint = range?.outPoint ?? store.outPoint;
      const analysisQueue = store.analysisQueue;
      if (inPoint == null || outPoint == null || outPoint <= inPoint || !sourcePath) {
        return false;
      }
      const dup = analysisQueue.some(
        (j) =>
          j.sourcePath === sourcePath &&
          Math.abs(j.inPoint - inPoint) < 0.05 &&
          Math.abs(j.outPoint - outPoint) < 0.05,
      );
      if (dup) return true;
      const job: AnalysisJob = {
        id: crypto.randomUUID(),
        sourcePath,
        inPoint,
        outPoint,
      };
      set({ analysisQueue: [...analysisQueue, job] });
      return true;
    },

    removeQueued: (id) => {
      set({ analysisQueue: get().analysisQueue.filter((j) => j.id !== id) });
    },

    updateQueued: (id, patch) => {
      set({
        analysisQueue: get().analysisQueue.map((job) => {
          if (job.id !== id) return job;
          const inPoint = patch.inPoint ?? job.inPoint;
          const outPoint = patch.outPoint ?? job.outPoint;
          if (!(outPoint > inPoint) || inPoint < 0) return job;
          return { ...job, inPoint, outPoint };
        }),
      });
    },

    recordLiveHits: (hits, timeSec) => {
      if (!hits.length) return;
      const prev = get().liveMarks;
      const next = [...prev];
      for (const hit of hits) {
        const bucket = Math.round(timeSec * 4) / 4;
        const bucketKey = `${hit.class_en}:${bucket}`;
        if (next.some((m) => m.bucketKey === bucketKey)) continue;
        next.push({
          id: `live-${bucketKey}-${String(hit.id || 'x').slice(0, 8)}`,
          timestamp: timeSec,
          class_en: hit.class_en,
          class_ru: hit.class_ru || hit.class_en,
          confidence: hit.confidence,
          bucketKey,
        });
      }
      set({ liveMarks: next.length > 600 ? next.slice(-600) : next });
    },

    clearLiveMarks: () => {
      set({ liveMarks: [] });
    },

    removeLiveMark: (id) => {
      set({ liveMarks: get().liveMarks.filter((m) => m.id !== id) });
    },

    markIn: (time) => {
      const t = time ?? get().playheadPosition;
      const outPoint = get().outPoint;
      set({
        inPoint: Math.max(0, t),
        outPoint: outPoint !== null && outPoint <= t ? null : outPoint,
      });
    },

    markOut: (time) => {
      const t = time ?? get().playheadPosition;
      const inPoint = get().inPoint;
      set({
        outPoint: Math.max(0, t),
        inPoint: inPoint !== null && inPoint >= t ? null : inPoint,
      });
    },

    clearInOut: () => {
      set({ inPoint: null, outPoint: null });
    },

    play: () => {
      if (get().playbackLockedReason) {
        return;
      }
      set({ playbackState: "playing" });
    },

    pause: () => {
      set({ playbackState: "paused" });
    },

    stop: () => {
      set({ playbackState: "stopped" });
    },

    togglePlayback: () => {
      const { playbackLockedReason, playbackState } = get();
      if (playbackLockedReason) {
        return;
      }
      if (playbackState === "playing") {
        set({ playbackState: "paused" });
      } else {
        set({ playbackState: "playing" });
      }
    },

    lockPlayback: (reason?: string) => {
      set({ playbackLockedReason: reason ?? "Applying effect" });
    },

    unlockPlayback: () => {
      set({ playbackLockedReason: null });
    },

    setPlaybackRate: (rate: number) => {
      set({ playbackRate: Math.max(0.1, Math.min(4.0, rate)) });
    },

    setPlayheadPosition: (position: number) => {
      const safe = Number.isFinite(position) && position > 0 ? position : 0;
      set({ playheadPosition: safe });
    },

    seekTo: (position: number) => {
      const { mediaDuration, playbackState } = get();
      const max = Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : Number.POSITIVE_INFINITY;
      const safePos = Number.isFinite(position) && position > 0 ? position : 0;
      const clampedPosition = Math.max(0, Math.min(max, safePos));
      set({
        playheadPosition: clampedPosition,
        seekEpoch: get().seekEpoch + 1,
        playbackState: playbackState === "playing" ? "paused" : playbackState,
      });
      get().scrollToPlayhead();
    },

    seekRelative: (delta: number) => {
      const { playheadPosition } = get();
      const safeDelta = Number.isFinite(delta) ? delta : 0;
      const newPosition = Math.max(0, playheadPosition + safeDelta);
      set({ playheadPosition: newPosition });
    },

    stepFrame: (deltaFrames: number) => {
      // Frame step uses seekTo semantics so the focused Viewer applies it via
      // applyVideoSeek (bumps seekEpoch + pauses), unlike seekRelative which
      // only moves the playhead marker. Default 30 fps; overridable later.
      const FRAME_DURATION_SEC = 1 / 30;
      const { playheadPosition, mediaDuration, playbackState } = get();
      const max = Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : Number.POSITIVE_INFINITY;
      const safePos = Number.isFinite(playheadPosition) && playheadPosition > 0 ? playheadPosition : 0;
      const safeDeltaFrames = Number.isFinite(deltaFrames) ? deltaFrames : 0;
      const newPosition = Math.max(0, Math.min(max, safePos + safeDeltaFrames * FRAME_DURATION_SEC));
      set({
        playheadPosition: newPosition,
        seekEpoch: get().seekEpoch + 1,
        playbackState: playbackState === "playing" ? "paused" : playbackState,
      });
    },

    seekToStart: () => {
      set({ playheadPosition: 0 });
    },

    seekToEnd: (duration: number) => {
      const safe = Number.isFinite(duration) && duration > 0 ? duration : 0;
      set({ playheadPosition: safe });
    },

    startScrubbing: (position: number) => {
      const { playbackState, mediaDuration } = get();
      const max = Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : Number.POSITIVE_INFINITY;
      const safePos = Number.isFinite(position) && position > 0 ? position : 0;
      const clamped = Math.max(0, Math.min(max, safePos));
      yoloDebug.noteScrub("start");
      set({
        isScrubbing: true,
        scrubPosition: clamped,
        playheadPosition: clamped,
        playbackState: playbackState === "playing" ? "paused" : playbackState,
      });
    },

    updateScrubPosition: (position: number) => {
      const { isScrubbing, mediaDuration } = get();
      if (!isScrubbing) return;
      const max = Number.isFinite(mediaDuration) && mediaDuration > 0 ? mediaDuration : Number.POSITIVE_INFINITY;
      const safePos = Number.isFinite(position) && position > 0 ? position : 0;
      const clamped = Math.max(0, Math.min(max, safePos));
      yoloDebug.noteScrub("move");
      set({
        scrubPosition: clamped,
        playheadPosition: clamped,
      });
    },

    endScrubbing: () => {
      const { scrubPosition, playheadPosition, isScrubbing } = get();
      if (!isScrubbing) return;
      const finalPos = scrubPosition ?? playheadPosition;
      yoloDebug.noteScrub("end");
      set({ isScrubbing: false, scrubPosition: null });
      get().seekTo(finalPos);
    },

    zoomIn: () => {
      const { pixelsPerSecond } = get();
      const newZoom = Math.min(pixelsPerSecond * 1.5, ZOOM_PRESETS.MAX);
      set({ pixelsPerSecond: newZoom });
      get().scrollToPlayhead();
    },

    zoomOut: () => {
      const { pixelsPerSecond } = get();
      const newZoom = Math.max(pixelsPerSecond / 1.5, ZOOM_PRESETS.MIN);
      set({ pixelsPerSecond: newZoom });
      get().scrollToPlayhead();
    },

    setZoom: (pixelsPerSecond: number) => {
      // Clamp zoom to valid range to ensure consistent rendering and prevent sub-pixel issues
      const clampedZoom = Math.max(
        ZOOM_PRESETS.MIN,
        Math.min(ZOOM_PRESETS.MAX, pixelsPerSecond),
      );
      set({ pixelsPerSecond: clampedZoom });
    },

    zoomToFit: (duration: number) => {
      const { viewportWidth } = get();
      if (Number.isFinite(duration) && duration > 0) {
        // Calculate zoom that fits entire timeline in viewport, leaving 100px margin for UI
        // Formula: pixels_per_second = available_width / duration_seconds
        const newZoom = Math.max(
          ZOOM_PRESETS.MIN,
          Math.min(ZOOM_PRESETS.MAX, (viewportWidth - 100) / duration),
        );
        set({
          pixelsPerSecond: newZoom,
          scrollX: 0, // Reset scroll to show beginning of timeline
        });
      }
    },

    resetZoom: () => {
      set({
        pixelsPerSecond: ZOOM_PRESETS.DEFAULT,
        scrollX: 0,
      });
    },

    setScrollX: (scrollX: number) => {
      set({ scrollX: Math.max(0, scrollX) });
    },

    setScrollY: (scrollY: number) => {
      set({ scrollY: Math.max(0, scrollY) });
    },

    scrollToPlayhead: () => {
      const { playheadPosition, pixelsPerSecond, viewportWidth, scrollX } =
        get();
      // Convert playhead time to pixel position using current zoom level
      const playheadPixels = playheadPosition * pixelsPerSecond;

      // Only scroll if playhead is outside visible viewport range
      // Check: playheadPixels < scrollX (left boundary) OR playheadPixels > scrollX + viewportWidth (right boundary)
      if (
        playheadPixels < scrollX ||
        playheadPixels > scrollX + viewportWidth
      ) {
        // Center playhead in viewport by placing it at 50% width from left edge
        const newScrollX = Math.max(0, playheadPixels - viewportWidth / 2);
        set({ scrollX: newScrollX });
      }
    },

    setViewportDimensions: (width: number, height: number) => {
      set({
        viewportWidth: width,
        viewportHeight: height,
      });
    },

    setTrackHeight: (height: number) => {
      // Update default track height within valid bounds (40px min for usability, 200px max for space)
      set({ trackHeight: Math.max(40, Math.min(200, height)) });
    },

    setTrackHeightById: (trackId: string, height: number) => {
      // Clamp individual track height to prevent extreme values affecting layout calculations
      const clampedHeight = Math.max(40, Math.min(200, height));
      // Use spread operator on trackHeights Map to trigger reactivity in Zustand
      set((state) => ({
        trackHeights: { ...state.trackHeights, [trackId]: clampedHeight },
      }));
    },

    getTrackHeight: (trackId: string, _trackType?: string) => {
      const { trackHeights, trackHeight } = get();
      const override = trackHeights[trackId];
      if (override !== undefined) return override;
      return trackHeight;
    },

    setLoopEnabled: (enabled: boolean) => {
      set({ loopEnabled: enabled });
    },

    setLoopRange: (start: number, end: number) => {
      if (start < end) {
        set({
          loopStart: Math.max(0, start),
          loopEnd: end,
        });
      }
    },

    timeToPixels: (time: number) => {
      const { pixelsPerSecond } = get();
      // Convert seconds to pixel distance: pixels = time * pixels_per_second
      return time * pixelsPerSecond;
    },

    pixelsToTime: (pixels: number) => {
      const { pixelsPerSecond } = get();
      // Convert pixel distance to seconds: time = pixels / pixels_per_second
      return pixels / pixelsPerSecond;
    },

    getVisibleTimeRange: () => {
      const { scrollX, viewportWidth, pixelsPerSecond } = get();
      // Calculate which time span is visible in the current viewport
      // start: leftmost pixel (scrollX) converted to time
      // end: rightmost pixel (scrollX + viewportWidth) converted to time
      return {
        start: scrollX / pixelsPerSecond,
        end: (scrollX + viewportWidth) / pixelsPerSecond,
      };
    },

    isTimeVisible: (time: number) => {
      const { start, end } = get().getVisibleTimeRange();
      return time >= start && time <= end;
    },

    toggleTrackExpanded: (trackId: string) => {
      set((state) => {
        const tracks = state.expandedTracks;
        const exists = tracks.includes(trackId);
        return { expandedTracks: exists
          ? tracks.filter(id => id !== trackId)
          : [...tracks, trackId]
        };
      });
    },

    setTrackExpanded: (trackId: string, expanded: boolean) => {
      set((state) => {
        const tracks = state.expandedTracks;
        return { expandedTracks: expanded
          ? tracks.includes(trackId) ? tracks : [...tracks, trackId]
          : tracks.filter(id => id !== trackId)
        };
      });
    },

    isTrackExpanded: (trackId: string) => {
      return get().expandedTracks.includes(trackId);
    },

    toggleClipKeyframesExpanded: (clipId: string) => {
      set((state) => {
        const clips = state.expandedClipKeyframes;
        const exists = clips.includes(clipId);
        return { expandedClipKeyframes: exists
          ? clips.filter(id => id !== clipId)
          : [...clips, clipId]
        };
      });
    },

    setClipKeyframesExpanded: (clipId: string, expanded: boolean) => {
      set((state) => {
        const clips = state.expandedClipKeyframes;
        return { expandedClipKeyframes: expanded
          ? clips.includes(clipId) ? clips : [...clips, clipId]
          : clips.filter(id => id !== clipId)
        };
      });
    },

    isClipKeyframesExpanded: (clipId: string) => {
      return get().expandedClipKeyframes.includes(clipId);
    },

    setKeyframeEditMode: (enabled: boolean) => {
      set({ keyframeEditMode: enabled });
    },
      }),
      {
        name: TIMELINE_WORKSPACE_STORAGE_KEY,
        partialize: (state) => ({
          trackHeight: state.trackHeight,
          trackHeights: state.trackHeights,
          analysisQueue: state.analysisQueue,
        }),
      },
    ),
  ),
);
