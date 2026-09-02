import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Camera,
  Crosshair,
  Hand,
  Maximize2,
  MoreHorizontal,
  MousePointer2,
  Pause,
  Pencil,
  Play,
  Trash2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { useViewerStore } from '../../store/useViewerStore';
import { useTimelineStore } from '../../store/timeline-store';
import {
  authHeaders,
  authToken,
  matchesMemory,
  toDetectedObject,
  useMuraveiStore,
} from '../../store/useMuraveiStore';
import type { BoundingBox, DetectedObject, PersistedDetection } from '../../types/muravei';
import { Button, IconButton, Menu, MenuItem, ToolbarGroup } from '../ui';
import { logger } from '../../services/logger';
import { formatMediaTime, mediaPathsMatch } from '../../lib/mediaPaths';
import { useAutoBatchScan } from '../../hooks/useAutoBatchScan';
import { yoloDebug } from '../../debug/yoloDebug';
import { YoloDebugOverlay } from '../debug/YoloDebugOverlay';
import { playRuleAlertTone, useRulesStore } from '../../store/useRulesStore';
import {
  useChangeDetectionStore,
  type ChangeType,
} from '../../store/useChangeDetectionStore';
import { CompareSyncModal } from './CompareSyncModal';
import { HeatmapOverlay } from './HeatmapOverlay';
import { BatchSegModal } from './BatchSegModal';
import type { BatchSegMask } from '../../store/useBatchSegStore';
import { parseSam3TextPrompt, useSam3Store } from '../../store/useSam3Store';
import { Sam3PropagateModal } from './Sam3PropagateModal';

interface ViewerProps {
  viewerId: string;
}

const TARGET_SIDE = 1024;
const MIN_SIDE = 640;
const JPEG_QUALITY = 0.85;
const TIME_EPS = 0.5;
const TIME_EPS_PAUSED = 2.0;
const LIVE_STALE = 2.0;
/** Block playhead publish after remount until seek settles or this elapses. */
const REMOUNT_PUBLISH_GUARD_MS = 500;
/** Intention/reality drift allowed for keyframe snap (seconds). */
const TIME_TRUTH_DRIFT = 0.5;
/** Hold YOLO off after scrub/seek ends (ms). Cleared only via timeout. */
const YOLO_SUSPEND_CLEAR_MS = 400;
/** Max YOLO send rate while video is paused (ms). */
const YOLO_PAUSED_THROTTLE_MS = 500;
/** Coalesce discrete seekEpoch clicks (ms). */
const DISCRETE_SEEK_DEBOUNCE_MS = 100;

/** Survives React unmount/remount of Viewer panels (mosaic layout changes). */
const viewerTimeCache = new Map<string, { path: string; t: number }>();

function rememberViewerTime(viewerId: string, path: string | null | undefined, t: number) {
  if (!path || !Number.isFinite(t) || t < 0) return;
  viewerTimeCache.set(viewerId, { path, t });
}

/** Last known playback time per viewer (for cross-panel Compare Sync). */
export function getViewerPlaybackTime(viewerId: string): number {
  return viewerTimeCache.get(viewerId)?.t ?? 0;
}
const MIN_BOX = 0.012;
const ACCENT = '#e87d0d';

type HandleKey = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w' | 'move' | 'draw';
type ViewTool = 'select' | 'pan';
type OverlayMode = 'detect' | 'seg';

type SegMask = {
  class: string;
  conf: number;
  polygon_norm: number[][];
};

function captureFrame(video: HTMLVideoElement): string | undefined {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw <= 0 || vh <= 0) return undefined;
  return captureFromSize(video, vw, vh);
}

function captureFromSize(
  source: CanvasImageSource,
  vw: number,
  vh: number,
): string | undefined {
  if (vw <= 0 || vh <= 0) return undefined;
  const long = Math.max(vw, vh);
  const short = Math.min(vw, vh);
  let scale = 1;
  if (long > TARGET_SIDE) scale = TARGET_SIDE / long;
  else if (short < MIN_SIDE) scale = MIN_SIDE / short;
  let w = Math.max(1, Math.round(vw * scale));
  let h = Math.max(1, Math.round(vh * scale));
  if (Math.max(w, h) > TARGET_SIDE) {
    const clamp = TARGET_SIDE / Math.max(w, h);
    w = Math.max(1, Math.round(w * clamp));
    h = Math.max(1, Math.round(h * clamp));
  }
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  ctx?.drawImage(source, 0, 0, w, h);
  return c.toDataURL('image/jpeg', JPEG_QUALITY);
}

function captureLiveImage(img: HTMLImageElement): string | undefined {
  const vw = img.naturalWidth;
  const vh = img.naturalHeight;
  if (vw <= 0 || vh <= 0) return undefined;
  return captureFromSize(img, vw, vh);
}

function captureThumb(video: HTMLVideoElement): string | undefined {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw <= 0 || vh <= 0) return undefined;
  const w = 160;
  const h = Math.max(1, Math.round((vh / vw) * w));
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  c.getContext('2d')?.drawImage(video, 0, 0, w, h);
  return c.toDataURL('image/jpeg', 0.7);
}

function clamp01(v: number): number {
  return Math.max(0, Math.min(1, v));
}

function normBox(b: BoundingBox): BoundingBox {
  const x1 = clamp01(Math.min(b.x1, b.x2));
  const y1 = clamp01(Math.min(b.y1, b.y2));
  const x2 = clamp01(Math.max(b.x1, b.x2));
  const y2 = clamp01(Math.max(b.y1, b.y2));
  return {
    x1,
    y1,
    x2: Math.max(x1 + MIN_BOX, x2),
    y2: Math.max(y1 + MIN_BOX, y2),
  };
}

function applyHandle(start: BoundingBox, handle: HandleKey, x: number, y: number, dx: number, dy: number): BoundingBox {
  const b = { ...start };
  switch (handle) {
    case 'nw':
      b.x1 = x;
      b.y1 = y;
      break;
    case 'n':
      b.y1 = y;
      break;
    case 'ne':
      b.x2 = x;
      b.y1 = y;
      break;
    case 'e':
      b.x2 = x;
      break;
    case 'se':
      b.x2 = x;
      b.y2 = y;
      break;
    case 's':
      b.y2 = y;
      break;
    case 'sw':
      b.x1 = x;
      b.y2 = y;
      break;
    case 'w':
      b.x1 = x;
      break;
    case 'move':
      b.x1 = start.x1 + dx;
      b.y1 = start.y1 + dy;
      b.x2 = start.x2 + dx;
      b.y2 = start.y2 + dy;
      break;
    default:
      break;
  }
  if (handle === 'move') {
    const w = start.x2 - start.x1;
    const h = start.y2 - start.y1;
    b.x1 = clamp01(b.x1);
    b.y1 = clamp01(b.y1);
    b.x2 = clamp01(b.x1 + w);
    b.y2 = clamp01(b.y1 + h);
    if (b.x2 >= 1) {
      b.x2 = 1;
      b.x1 = clamp01(1 - w);
    }
    if (b.y2 >= 1) {
      b.y2 = 1;
      b.y1 = clamp01(1 - h);
    }
    return b;
  }
  return normBox(b);
}

function handlePos(b: BoundingBox, key: Exclude<HandleKey, 'move' | 'draw'>): { x: number; y: number } {
  const mx = (b.x1 + b.x2) / 2;
  const my = (b.y1 + b.y2) / 2;
  const map: Record<string, { x: number; y: number }> = {
    nw: { x: b.x1, y: b.y1 },
    n: { x: mx, y: b.y1 },
    ne: { x: b.x2, y: b.y1 },
    e: { x: b.x2, y: my },
    se: { x: b.x2, y: b.y2 },
    s: { x: mx, y: b.y2 },
    sw: { x: b.x1, y: b.y2 },
    w: { x: b.x1, y: my },
  };
  return map[key];
}

const HANDLES: Exclude<HandleKey, 'move' | 'draw'>[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

function nearTime(
  rows: PersistedDetection[],
  source: string,
  timeSec: number,
  eps: number,
): PersistedDetection[] {
  return rows.filter(
    (d) =>
      mediaPathsMatch(d.source_video, source) &&
      !d.is_deleted &&
      Math.abs(d.time_sec - timeSec) <= eps,
  );
}

export const Viewer: React.FC<ViewerProps> = ({ viewerId }) => {
  const viewer = useViewerStore((s) => s.viewers[viewerId]);
  const setSource = useViewerStore((s) => s.setSource);
  const setSourceMode = useViewerStore((s) => s.setSourceMode);
  const setLiveUrl = useViewerStore((s) => s.setLiveUrl);
  const setLiveActive = useViewerStore((s) => s.setLiveActive);
  const setPlaying = useViewerStore((s) => s.setPlaying);
  const setFocusedViewer = useViewerStore((s) => s.setFocusedViewer);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const showMotion = useViewerStore((s) => s.showMotion);
  const setShowMotion = useViewerStore((s) => s.setShowMotion);
  const compareMode = useViewerStore((s) => s.compareMode);
  const setCompareMode = useViewerStore((s) => s.setCompareMode);
  const syncPlayhead = useViewerStore((s) => s.syncPlayhead);
  const setSyncPlayhead = useViewerStore((s) => s.setSyncPlayhead);
  const syncMode = useTimelineStore((s) => s.syncMode);
  const setSyncMode = useTimelineStore((s) => s.setSyncMode);
  const setLastObjects = useViewerStore((s) => s.setLastObjects);
  const lastObjects = useViewerStore((s) => s.lastObjects);
  const cdResult = useChangeDetectionStore((s) => s.result);
  const cdLoading = useChangeDetectionStore((s) => s.loading);
  const cdRunAnalysis = useChangeDetectionStore((s) => s.runAnalysis);
  const cdClear = useChangeDetectionStore((s) => s.clear);
  const cdActiveHighlight = useChangeDetectionStore((s) => s.activeHighlight);
  const cdSeekTargets = useChangeDetectionStore((s) => s.seekTargets);
  const cdRequestSeek = useChangeDetectionStore((s) => s.requestSeek);
  const showHeatmap = useChangeDetectionStore((s) => s.showHeatmap);
  const setShowHeatmap = useChangeDetectionStore((s) => s.setShowHeatmap);
  const [syncModalOpen, setSyncModalOpen] = useState(false);
  const [batchSegOpen, setBatchSegOpen] = useState(false);
  const [samPropOpen, setSamPropOpen] = useState(false);
  const analysisConfig = useMuraveiStore((s) => s.analysisConfig);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  useAutoBatchScan(viewer?.sourcePath ?? undefined, isAuthenticated);
  const editMode = useMuraveiStore((s) => s.editMode);
  const setEditMode = useMuraveiStore((s) => s.setEditMode);
  const detections = useMuraveiStore((s) => s.detections);
  const suppressedDetections = useMuraveiStore((s) => s.suppressedDetections);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const classCatalog = useMuraveiStore((s) => s.classCatalog);
  const setActiveDetection = useMuraveiStore((s) => s.setActiveDetection);
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const loadClassCatalog = useMuraveiStore((s) => s.loadClassCatalog);
  const commitFrame = useMuraveiStore((s) => s.commitFrame);
  const createDetection = useMuraveiStore((s) => s.createDetection);
  const patchDetection = useMuraveiStore((s) => s.patchDetection);
  const dismissDetection = useMuraveiStore((s) => s.dismissDetection);
  const seekEpoch = useTimelineStore((s) => s.seekEpoch);
  const playbackState = useTimelineStore((s) => s.playbackState);
  const playbackRate = useTimelineStore((s) => s.playbackRate);
  const inPoint = useTimelineStore((s) => s.inPoint);
  const outPoint = useTimelineStore((s) => s.outPoint);
  const markIn = useTimelineStore((s) => s.markIn);
  const markOut = useTimelineStore((s) => s.markOut);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);
  const setPlayheadPosition = useTimelineStore((s) => s.setPlayheadPosition);
  const setMediaDuration = useTimelineStore((s) => s.setMediaDuration);
  const setPreviewFrame = useTimelineStore((s) => s.setPreviewFrame);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const isScrubbing = useTimelineStore((s) => s.isScrubbing);
  const startScrubbing = useTimelineStore((s) => s.startScrubbing);
  const updateScrubPosition = useTimelineStore((s) => s.updateScrubPosition);
  const endScrubbing = useTimelineStore((s) => s.endScrubbing);
  const timelinePlay = useTimelineStore((s) => s.play);
  const timelinePause = useTimelineStore((s) => s.pause);

  const videoRef = useRef<HTMLVideoElement>(null);
  const liveImgRef = useRef<HTMLImageElement>(null);
  const stageParentRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const frameRef = useRef(0);
  const liveRef = useRef<DetectedObject[]>([]);
  const inFlightRef = useRef(false);
  const lastPausedAt = useRef(-1);
  const lastPreviewAt = useRef(0);
  const ignoreSeek = useRef(false);
  /** Target time of in-flight discrete/scrub seek; cleared only on seeked. Last-wins. */
  const pendingSeek = useRef<number | null>(null);
  /** Alias of pending target for overlay gating (same ref). */
  const pendingSeekTime = pendingSeek;
  const seekRetryRef = useRef(0);
  /** Until this timestamp (performance.now), primary must not publish playhead. */
  const remountGuardUntil = useRef(0);
  /** Compare Sync slave offset (seconds); kept as ref per prompt. */
  const syncOffsetRef = useRef(0);
  /** Last known decoded time for this viewer instance (also mirrored to viewerTimeCache). */
  const lastKnownTime = useRef(0);
  /** YOLO WS reconnect generation + timer (avoid double sockets / infinite retries). */
  const wsGenRef = useRef(0);
  const wsReconnectTimerRef = useRef<number | null>(null);
  const wsReconnectAttemptRef = useRef(0);
  /** YOLO scrub/seek suspend: cleared only by setTimeout(YOLO_SUSPEND_CLEAR_MS). */
  const yoloSuspendRef = useRef(false);
  const yoloSuspendClearTimerRef = useRef<number | null>(null);
  const lastSeekOrScrubAt = useRef(0);
  const lastPausedSendAt = useRef(0);
  const isLiveRef = useRef(false);
  const [seekInFlight, setSeekInFlight] = useState(false);
  const dragRef = useRef<{
    handle: HandleKey;
    id: string | null;
    start: BoundingBox;
    originX: number;
    originY: number;
    persisted: boolean;
  } | null>(null);

  const [liveObjects, setLiveObjects] = useState<DetectedObject[]>([]);
  const [frozenLive, setFrozenLive] = useState<DetectedObject[]>([]);
  const [liveStamp, setLiveStamp] = useState(-1);
  const freezeTimeRef = useRef(-1);
  const [paused, setPaused] = useState(true);
  const [timeSec, setTimeSec] = useState(0);
  const [mode, setMode] = useState<string>('offline');
  const [status, setStatus] = useState('idle');
  const [inferKind, setInferKind] = useState<string>('—');
  const [inferN, setInferN] = useState(0);
  const [inferMs, setInferMs] = useState(0);
  const [yoloHud, setYoloHud] = useState<'ready' | 'warn' | 'error'>('warn');
  const [stage, setStage] = useState({ w: 0, h: 0 });
  const [draft, setDraft] = useState<BoundingBox | null>(null);
  const [manualClassId, setManualClassId] = useState<number | null>(null);
  const [committing, setCommitting] = useState(false);
  const [dragPreview, setDragPreview] = useState<{ id: string; bbox: BoundingBox } | null>(null);
  const dragPreviewRef = useRef<{ id: string; bbox: BoundingBox } | null>(null);
  const [viewTool, setViewTool] = useState<ViewTool>('select');
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const panDrag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const [recOn, setRecOn] = useState(false);
  const [recBusy, setRecBusy] = useState(false);
  const [recStartedAt, setRecStartedAt] = useState<number | null>(null);
  const [recElapsed, setRecElapsed] = useState(0);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const [toolbarNarrow, setToolbarNarrow] = useState(false);
  const [toolbarMoreOpen, setToolbarMoreOpen] = useState(false);
  const [liveDraft, setLiveDraft] = useState('');
  const [liveBusy, setLiveBusy] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);
  const [scrubDragging, setScrubDragging] = useState(false);
  const [localDuration, setLocalDuration] = useState(0);
  const [overlayMode, setOverlayMode] = useState<OverlayMode>('detect');
  const [segReady, setSegReady] = useState(false);
  const [segLoaded, setSegLoaded] = useState(false);
  const [segHint, setSegHint] = useState<string | null>(null);
  const [segMasks, setSegMasks] = useState<SegMask[]>([]);
  const [segBusy, setSegBusy] = useState(false);
  const segGenRef = useRef(0);
  const overlayModeRef = useRef<OverlayMode>('detect');
  const samReady = useSam3Store((s) => s.ready);
  const samLoaded = useSam3Store((s) => s.loaded);
  const samBusy = useSam3Store((s) => s.busy);
  const samTool = useSam3Store((s) => s.tool);
  const samHint = useSam3Store((s) => s.hint);
  const samNotice = useSam3Store((s) => s.lastUnloadNotice);
  const refreshSamStatus = useSam3Store((s) => s.refreshStatus);
  const loadSam3 = useSam3Store((s) => s.load);
  const unloadSam3 = useSam3Store((s) => s.unload);
  const setSamTool = useSam3Store((s) => s.setTool);
  const setSamHint = useSam3Store((s) => s.setHint);
  const inferSam3 = useSam3Store((s) => s.infer);
  const clearSamNotice = useSam3Store((s) => s.clearNotice);
  const markSamUnloadedByYolo = useSam3Store((s) => s.markUnloadedByYolo);
  const samLastPrompt = useSam3Store((s) => s.lastPrompt);
  const samTextPrompt = useSam3Store((s) => s.textPrompt);
  const setSamTextPrompt = useSam3Store((s) => s.setTextPrompt);
  const hasSamSeed = Boolean(
    samLastPrompt?.points?.length ||
      samLastPrompt?.bboxes?.length ||
      samLastPrompt?.text?.length,
  );

  const isLive = viewer?.sourceMode === 'live' && Boolean(viewer?.liveActive);
  isLiveRef.current = isLive;
  const yoloAlwaysOn =
    Boolean(isAuthenticated) &&
    (Boolean(viewer?.sourcePath) || isLive) &&
    overlayMode === 'detect';
  const sourceVideo = isLive
    ? `live:${viewerId}`
    : viewer?.sourcePath || 'local';

  const clearYoloSuspendTimer = () => {
    if (yoloSuspendClearTimerRef.current != null) {
      window.clearTimeout(yoloSuspendClearTimerRef.current);
      yoloSuspendClearTimerRef.current = null;
    }
  };

  const armYoloSuspend = () => {
    yoloSuspendRef.current = true;
    lastSeekOrScrubAt.current = performance.now();
    clearYoloSuspendTimer();
    yoloDebug.setSuspend(true);
  };

  const scheduleYoloSuspendClear = () => {
    lastSeekOrScrubAt.current = performance.now();
    clearYoloSuspendTimer();
    yoloDebug.setSuspend(true, YOLO_SUSPEND_CLEAR_MS);
    yoloSuspendClearTimerRef.current = window.setTimeout(() => {
      yoloSuspendClearTimerRef.current = null;
      yoloSuspendRef.current = false;
      yoloDebug.setSuspend(false);
    }, YOLO_SUSPEND_CLEAR_MS);
  };

  useEffect(() => {
    liveRef.current = liveObjects;
  }, [liveObjects]);

  useEffect(() => {
    if (manualClassId != null || classCatalog.length === 0) return;
    const firstEnabled = classCatalog.find((item) => item.enabled !== false);
    setManualClassId(firstEnabled?.id ?? null);
  }, [classCatalog, manualClassId]);

  // Scrub flag → arm; release only via 400ms timeout (not immediately on endScrubbing)
  useEffect(() => {
    if (isLive) return;
    if (isScrubbing) armYoloSuspend();
    else if (yoloSuspendRef.current) scheduleYoloSuspendClear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isScrubbing, isLive]);

  useEffect(() => {
    return () => clearYoloSuspendTimer();
  }, []);

  useEffect(() => {
    const el = toolbarRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setToolbarNarrow(w < 560);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!toolbarMoreOpen) return;
    const onDoc = () => setToolbarMoreOpen(false);
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [toolbarMoreOpen]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void loadClassCatalog();
    const path = viewer?.sourcePath;
    if (path && focusedViewerId === viewerId) void hydrateDetections(path);
  }, [
    isAuthenticated,
    hydrateDetections,
    loadClassCatalog,
    viewer?.sourcePath,
    focusedViewerId,
    viewerId,
  ]);

  useEffect(() => {
    if (!isAuthenticated || viewer?.sourceMode !== 'live' || !viewer.liveActive) return;
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(`/api/live/${encodeURIComponent(viewerId)}/status`, {
          headers: authHeaders(),
        });
        const data = (await res.json().catch(() => ({}))) as { active?: boolean };
        if (!cancelled && (!res.ok || !data.active)) {
          setLiveActive(viewerId, false);
          setPaused(true);
          setLiveError('Live-поток завершён');
        }
      } catch {
        // Keep the stream open through transient backend/network failures.
      }
    };
    void check();
    const timer = window.setInterval(() => void check(), 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    isAuthenticated,
    setLiveActive,
    viewer?.liveActive,
    viewer?.sourceMode,
    viewerId,
  ]);

  const layoutStage = useCallback(() => {
    const parent = stageParentRef.current;
    if (!parent) return;
    const pw = parent.clientWidth;
    const ph = parent.clientHeight;
    const video = videoRef.current;
    const liveImg = liveImgRef.current;
    const vw = isLive ? liveImg?.naturalWidth || 0 : video?.videoWidth || 0;
    const vh = isLive ? liveImg?.naturalHeight || 0 : video?.videoHeight || 0;
    if (!vw || !vh || !pw || !ph) {
      setStage({ w: isLive ? pw : 0, h: isLive ? ph : 0 });
      return;
    }
    const scale = Math.min(pw / vw, ph / vh);
    setStage({ w: Math.max(1, vw * scale), h: Math.max(1, vh * scale) });
  }, [isLive]);

  useEffect(() => {
    const parent = stageParentRef.current;
    if (!parent || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => layoutStage());
    ro.observe(parent);
    layoutStage();
    return () => ro.disconnect();
  }, [layoutStage, viewer?.sourceUrl, isLive, viewer?.liveActive]);

  useEffect(() => {
    const parent = stageParentRef.current;
    if (!parent) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
      setZoom((z) => Math.min(8, Math.max(1, Number((z * factor).toFixed(3)))));
      setViewTool('pan');
    };
    parent.addEventListener('wheel', onWheel, { passive: false });
    return () => parent.removeEventListener('wheel', onWheel);
  }, [viewer?.sourcePath]);

  const isPrimaryDriver = focusedViewerId === viewerId;
  const isCompareSyncSlave =
    compareMode &&
    (syncMode === 'follow' || syncPlayhead) &&
    viewerId !== focusedViewerId &&
    !isLive &&
    Boolean(viewer?.sourcePath);
  const shouldSyncToPlayhead = isPrimaryDriver || isCompareSyncSlave;
  /** Only focused primary may write playhead intention into the store. */
  const canPublishPlayhead = isPrimaryDriver;
  const displayEps = paused || scrubDragging ? TIME_EPS_PAUSED : TIME_EPS;
  const scrubDuration =
    localDuration > 0 ? localDuration : mediaDuration > 0 ? mediaDuration : 0;
  // Reality: decoded frame time. Intention (playhead) is for clocks/scrub UI only.
  const overlayTimeSec = timeSec;
  const displayScrubTime = shouldSyncToPlayhead ? playheadPosition : timeSec;

  const isSeekBlocked = () => {
    const video = videoRef.current;
    return pendingSeekTime.current != null || Boolean(video?.seeking);
  };

  /** File-video only; Live path must never be gated by scrub/seek suspend. */
  const shouldSkipYoloFile = (reasonOut?: { reason: string }): boolean => {
    if (yoloSuspendRef.current) {
      if (reasonOut) reasonOut.reason = 'suspend';
      return true;
    }
    if (performance.now() - lastSeekOrScrubAt.current < YOLO_SUSPEND_CLEAR_MS) {
      if (reasonOut) reasonOut.reason = 'cooldown';
      return true;
    }
    if (useTimelineStore.getState().isScrubbing || isSeekBlocked()) {
      if (reasonOut) reasonOut.reason = 'scrub/seek';
      return true;
    }
    return false;
  };

  const isPublishBlocked = () => {
    if (!canPublishPlayhead) return true;
    if (performance.now() < remountGuardUntil.current) return true;
    if (ignoreSeek.current || pendingSeekTime.current != null) return true;
    const video = videoRef.current;
    if (video?.seeking) return true;
    return false;
  };

  const resolveRestoreTarget = () => {
    const path = viewer?.sourcePath ?? '';
    const store = useTimelineStore.getState();
    const storePos = store.playheadPosition;
    const pendingJump = store.pendingJump;
    const cached = viewerTimeCache.get(viewerId);
    const offset = isCompareSyncSlave ? syncOffsetRef.current : 0;

    // Detection jump after source change wins over remount cache
    if (pendingJump != null) {
      return Math.max(0, pendingJump + (isCompareSyncSlave ? offset : 0));
    }

    if (isCompareSyncSlave) {
      return Math.max(0, storePos + offset);
    }

    // Remount: prefer lastKnown/cache when store was corrupted downward by early timeupdate
    const known =
      lastKnownTime.current > 0
        ? lastKnownTime.current
        : cached?.path === path
          ? cached.t
          : 0;
    if (known > 0 && path && cached?.path === path) {
      if (storePos <= TIME_TRUTH_DRIFT && known > TIME_TRUTH_DRIFT) return known;
      if (known - storePos > 1.0) return known;
      return Math.max(storePos, known);
    }
    if (storePos > 0) return storePos;
    if (known > 0) return known;
    return 0;
  };

  const settleSeek = (video: HTMLVideoElement) => {
    pendingSeekTime.current = null;
    ignoreSeek.current = false;
    setSeekInFlight(false);
    const t = video.currentTime;
    lastKnownTime.current = t;
    rememberViewerTime(viewerId, viewer?.sourcePath, t);
    setTimeSec(t);
    setLiveObjects([]);
    setFrozenLive([]);
    setLiveStamp(-1);
    lastPausedAt.current = -1;
    remountGuardUntil.current = 0;
    if (useTimelineStore.getState().isScrubbing) {
      armYoloSuspend();
    } else {
      scheduleYoloSuspendClear();
    }
    if (isPrimaryDriver) {
      // Repair intention to match reality; bump epoch so Compare Sync slaves follow
      const intention = useTimelineStore.getState().playheadPosition;
      if (Math.abs(intention - t) > TIME_TRUTH_DRIFT) {
        seekTo(t);
      }
      const thumb = captureThumb(video);
      if (thumb) setPreviewFrame(thumb);
    }
  };

  const applyVideoSeek = (target: number, opts?: { force?: boolean; useFastSeek?: boolean }) => {
    const video = videoRef.current;
    if (!video) return false;
    if (video.readyState < 1) return false;
    const dur = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    const clamped = dur > 0 ? Math.min(Math.max(0, target), dur) : Math.max(0, target);
    const epsilon = opts?.useFastSeek || isScrubbing ? 0.12 : opts?.force ? 0.02 : 0.04;
    if (Math.abs(video.currentTime - clamped) <= epsilon && !video.seeking) {
      pendingSeekTime.current = null;
      ignoreSeek.current = false;
      setSeekInFlight(false);
      lastKnownTime.current = video.currentTime;
      rememberViewerTime(viewerId, viewer?.sourcePath, video.currentTime);
      setTimeSec(video.currentTime);
      remountGuardUntil.current = 0;
      if (!isLive) {
        if (useTimelineStore.getState().isScrubbing) armYoloSuspend();
        else scheduleYoloSuspendClear();
      }
      return true;
    }
    if (!isLive) armYoloSuspend();
    ignoreSeek.current = true;
    pendingSeekTime.current = clamped;
    setSeekInFlight(true);
    if (opts?.useFastSeek && typeof video.fastSeek === 'function') {
      try {
        video.fastSeek(clamped);
      } catch {
        video.currentTime = clamped;
      }
    } else {
      video.currentTime = clamped;
    }
    return true;
  };

  const restoreAfterMount = () => {
    if (isLive) return;
    if (!viewer?.sourcePath) return;
    remountGuardUntil.current = performance.now() + REMOUNT_PUBLISH_GUARD_MS;
    const pendingJump = useTimelineStore.getState().pendingJump;
    if (pendingJump != null) {
      try {
        const target = isCompareSyncSlave
          ? pendingJump + syncOffsetRef.current
          : pendingJump;
        applyVideoSeek(target, { force: true, useFastSeek: false });
      } finally {
        useTimelineStore.getState().setPendingJump(null);
      }
      return;
    }
    const target = resolveRestoreTarget();
    if (target <= 0 && !isCompareSyncSlave) return;
    applyVideoSeek(target, { force: true, useFastSeek: false });
  };

  const scrubTimeFromClientX = (clientX: number, el: HTMLElement) => {
    if (scrubDuration <= 0) return 0;
    const r = el.getBoundingClientRect();
    const t = ((clientX - r.left) / Math.max(1, r.width)) * scrubDuration;
    return Math.max(0, Math.min(scrubDuration, t));
  };

  const persistedNear = useMemo(
    () =>
      nearTime(detections, sourceVideo, overlayTimeSec, displayEps).map((r) =>
        toDetectedObject(r, classCatalog),
      ),
    [detections, sourceVideo, overlayTimeSec, displayEps, classCatalog],
  );

  const overlayObjects = useMemo(() => {
    // Hide bbox while seek in flight — draw only after seeked (stable frame)
    if (seekInFlight || pendingSeekTime.current != null) return [];
    const notDeleted = (objs: DetectedObject[]) =>
      objs.filter(
        (o) =>
          !suppressedDetections.some((s) => s.id === o.id) &&
          !matchesMemory(o, suppressedDetections, sourceVideo, overlayTimeSec),
      );
    const notSaved = (objs: DetectedObject[]) =>
      objs.filter((o) => !matchesMemory(o, detections, sourceVideo, overlayTimeSec));
    const liveFresh = Math.abs(overlayTimeSec - liveStamp) <= LIVE_STALE;
    const freezeFresh = editMode && Math.abs(overlayTimeSec - freezeTimeRef.current) <= TIME_EPS;
    const livePool = notDeleted(freezeFresh && frozenLive.length ? frozenLive : liveFresh ? liveObjects : []);
    const extra = notSaved(livePool);
    const persisted = persistedNear;
    const base = [...persisted, ...extra].sort((a, b) => {
      const aa = (a.bbox.x2 - a.bbox.x1) * (a.bbox.y2 - a.bbox.y1);
      const ba = (b.bbox.x2 - b.bbox.x1) * (b.bbox.y2 - b.bbox.y1);
      return ba - aa;
    });
    if (!dragPreview) return base;
    return base.map((o) => (o.id === dragPreview.id ? { ...o, bbox: dragPreview.bbox } : o));
  }, [
    editMode,
    liveObjects,
    liveStamp,
    frozenLive,
    persistedNear,
    dragPreview,
    suppressedDetections,
    detections,
    sourceVideo,
    overlayTimeSec,
    seekInFlight,
  ]);

  const CHANGE_COLORS: Record<ChangeType, string> = {
    new: '#22c55e',
    removed: '#ef4444',
    moved: '#eab308',
  };

  const changeOverlays = useMemo(() => {
    if (!compareMode || overlayMode === 'seg' || !cdResult) return [];
    const hl = cdActiveHighlight;
    const out: {
      id: string;
      changeType: ChangeType;
      bbox: BoundingBox;
      class_name: string;
      highlighted: boolean;
    }[] = [];

    if (viewerId === 'viewer-1') {
      for (const item of cdResult.removed) {
        out.push({
          id: item.id,
          changeType: 'removed',
          bbox: item.bbox,
          class_name: item.class_name || '?',
          highlighted: hl?.kind === 'removed' && hl.id === item.id,
        });
      }
      for (const m of cdResult.matches) {
        if (m.status !== 'moved') continue;
        out.push({
          id: m.before_id,
          changeType: 'moved',
          bbox: m.before_bbox,
          class_name: m.class_name || '?',
          highlighted: hl?.kind === 'moved' && hl.id === m.before_id,
        });
      }
    }
    if (viewerId === 'viewer-2') {
      for (const item of cdResult.new) {
        out.push({
          id: item.id,
          changeType: 'new',
          bbox: item.bbox,
          class_name: item.class_name || '?',
          highlighted: hl?.kind === 'new' && hl.id === item.id,
        });
      }
      for (const m of cdResult.matches) {
        if (m.status !== 'moved') continue;
        out.push({
          id: m.before_id,
          changeType: 'moved',
          bbox: m.after_bbox,
          class_name: m.class_name || '?',
          highlighted: hl?.kind === 'moved' && hl.id === m.before_id,
        });
      }
    }
    return out;
  }, [compareMode, overlayMode, cdResult, cdActiveHighlight, viewerId]);

  const commitableLive = useMemo(() => {
    const pool = frozenLive.length ? frozenLive : liveObjects;
    return pool.filter(
      (o) =>
        !matchesMemory(o, suppressedDetections, sourceVideo, overlayTimeSec) &&
        !matchesMemory(o, detections, sourceVideo, overlayTimeSec),
    );
  }, [frozenLive, liveObjects, suppressedDetections, detections, sourceVideo, overlayTimeSec]);

  useEffect(() => {
    if (!yoloAlwaysOn) {
      if (wsReconnectTimerRef.current) {
        window.clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
      wsGenRef.current += 1;
      wsReconnectAttemptRef.current = 0;
      wsRef.current?.close();
      wsRef.current = null;
      setStatus(isAuthenticated ? 'idle' : 'unauthorized');
      setYoloHud(isAuthenticated ? 'warn' : 'error');
      return;
    }
    const token = localStorage.getItem('muravei-token');
    if (!token) {
      setStatus('unauthorized');
      setYoloHud('error');
      return;
    }

    const gen = ++wsGenRef.current;
    wsReconnectAttemptRef.current = 0;
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${window.location.host}/ws/detect/${viewerId}?token=${encodeURIComponent(token)}`;

    const clearReconnectTimer = () => {
      if (wsReconnectTimerRef.current) {
        window.clearTimeout(wsReconnectTimerRef.current);
        wsReconnectTimerRef.current = null;
      }
    };

    const connect = () => {
      if (wsGenRef.current !== gen) return;
      const existing = wsRef.current;
      if (
        existing &&
        (existing.readyState === WebSocket.OPEN ||
          existing.readyState === WebSocket.CONNECTING)
      ) {
        return;
      }
      if (existing) {
        try {
          existing.close();
        } catch {
          /* ignore */
        }
        wsRef.current = null;
      }
      inFlightRef.current = false;
      const ws = new WebSocket(url);
      wsRef.current = ws;
      ws.onopen = () => {
        if (wsGenRef.current !== gen) return;
        wsReconnectAttemptRef.current = 0;
        inFlightRef.current = false;
        lastPausedAt.current = -1;
        setStatus('connected');
        setYoloHud('ready');
        logger.info('yolo', `${viewerId}: WS connected`);
      };
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        inFlightRef.current = false;
        lastPausedAt.current = -1;
        setStatus('disconnected');
        setYoloHud('warn');
        logger.warn('yolo', `${viewerId}: WS disconnected`);
        if (wsGenRef.current !== gen) return;
        if (!yoloAlwaysOn) return;
        const attempt = wsReconnectAttemptRef.current;
        if (attempt >= 10) {
          logger.error('yolo', `${viewerId}: WS reconnect gave up after 10 attempts`);
          setStatus('reconnect-failed');
          setYoloHud('error');
          return;
        }
        const delay = Math.min(8000, 500 * 2 ** attempt);
        wsReconnectAttemptRef.current = attempt + 1;
        clearReconnectTimer();
        wsReconnectTimerRef.current = window.setTimeout(() => {
          wsReconnectTimerRef.current = null;
          connect();
        }, delay);
      };
      ws.onerror = () => {
        setStatus('error');
        setYoloHud('error');
        logger.error('yolo', `${viewerId}: WS error`);
      };
      ws.onmessage = (ev) => {
        inFlightRef.current = false;
        // File-video: drop late replies before parse (scrub/seek suspend)
        if (!isLiveRef.current) {
          const reason = { reason: '' };
          if (shouldSkipYoloFile(reason)) {
            yoloDebug.noteWsBlocked(reason.reason);
            console.debug('[YOLO] skip:', reason.reason);
            return;
          }
        }
        yoloDebug.noteWsAllowed();
        try {
          const data = JSON.parse(ev.data);
          if (data.dropped) {
            lastPausedAt.current = -1;
            logger.warn('yolo', `${viewerId}: frame dropped (queue full)`);
            return;
          }
          if (data.error) {
            setStatus(String(data.error));
            setYoloHud('error');
            if (data.mode) setMode(data.mode);
            logger.error('yolo', `${viewerId}: ${String(data.error)}`);
            return;
          }
          // Drop stale YOLO results while seek is in flight
          if (!isLiveRef.current && isSeekBlocked()) {
            yoloDebug.noteWsBlocked('seek-blocked-late');
            console.debug('[YOLO] skip:', 'seek-blocked-late');
            return;
          }
          const kind = String(data.kind || data.model || '—');
          const n = typeof data.n === 'number' ? data.n : (data.objects ?? []).length;
          const ms = typeof data.ms === 'number' ? data.ms : 0;
          setInferKind(kind);
          setInferN(n);
          setInferMs(ms);
          setMode(data.mode ?? 'ready');
          setYoloHud('ready');
          const dets = (data.objects ?? []) as DetectedObject[];
          setLiveObjects(dets);
          setLastObjects(viewerId, dets);
          const stamp = typeof data.timeSec === 'number' ? data.timeSec : timeSec;
          setLiveStamp(stamp);
          const ruleMatches = useRulesStore.getState().evaluate(dets, sourceVideo, stamp);
          if (ruleMatches.length) {
            for (const { rule } of ruleMatches) {
              const soundType = rule.soundType ?? (rule.sound ? 'beep' : 'none');
              if (soundType === 'none') continue;
              const volume = rule.soundVolume ?? 70;
              playRuleAlertTone(soundType, volume);
            }
            const frameJpeg = isLiveRef.current
              ? liveImgRef.current
                ? captureLiveImage(liveImgRef.current)
                : undefined
              : videoRef.current
                ? captureFrame(videoRef.current)
                : undefined;
            void commitFrame({
              source_video: sourceVideo,
              time_sec: stamp,
              frame_idx: frameRef.current,
              frame_jpeg: frameJpeg,
              objects: ruleMatches.map(({ object }) => ({
                class_id: object.class_id ?? 0,
                class_name: object.class_en || object.class_ru,
                confidence: object.confidence,
                bbox: object.bbox,
              })),
            });
          }
          if (viewerId === focusedViewerId && dets.length && !isSeekBlocked()) {
            useTimelineStore.getState().recordLiveHits(
              dets.map((d) => ({
                id: d.id,
                class_en: d.class_en,
                class_ru: d.class_ru,
                confidence: d.confidence,
              })),
              stamp,
            );
          }
          setStatus(`connected · ${n} obj · ${ms}ms`);
          logger.verbose(
            'yolo',
            `${viewerId}: kind=${kind} n=${n} ms=${ms} nms=${data.nms_mode ?? '?'}`,
          );
        } catch (err) {
          console.error('detect ws parse', err);
          logger.error('yolo', `${viewerId}: parse error`);
        }
      };
    };

    connect();

    return () => {
      clearReconnectTimer();
      wsGenRef.current += 1;
      wsReconnectAttemptRef.current = 0;
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [
    yoloAlwaysOn,
    viewerId,
    isAuthenticated,
    focusedViewerId,
    setLastObjects,
    sourceVideo,
    commitFrame,
  ]);

  useEffect(() => {
    if (!yoloAlwaysOn || (!viewer?.sourcePath && !isLive)) return;
    let raf = 0;
    let lastSent = 0;
    lastPausedAt.current = -1;
    lastPausedSendAt.current = 0;
    const step = Math.max(1, analysisConfig.frameStep || 15);

    const sendFrame = () => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      if (inFlightRef.current) return false;
      if (dragRef.current) return false;
      // Live: never gate on scrub/seek suspend
      if (!isLive) {
        const reason = { reason: '' };
        if (shouldSkipYoloFile(reason)) {
          console.debug('[YOLO] skip:', reason.reason);
          return false;
        }
      }
      let image: string | undefined;
      let tSec = 0;
      if (isLive) {
        const img = liveImgRef.current;
        if (!img || img.naturalWidth <= 0) return false;
        image = captureLiveImage(img);
        tSec = performance.now() / 1000;
      } else {
        const video = videoRef.current;
        if (!video || video.readyState < 2 || video.videoWidth <= 0) return false;
        if (video.seeking || pendingSeekTime.current != null) return false;
        image = captureFrame(video);
        tSec = video.currentTime ?? 0;
      }
      if (!image) return false;
      frameRef.current += 1;
      inFlightRef.current = true;
      yoloDebug.noteInfer();
      ws.send(
        JSON.stringify({
          confidence: analysisConfig.confidenceThreshold,
          frameIdx: frameRef.current,
          timeSec: tSec,
          image,
        }),
      );
      return true;
    };

    const tick = (t: number) => {
      raf = requestAnimationFrame(tick);
      if (dragRef.current) return;
      if (isLive) {
        if (t - lastSent < (1000 / 30) * step) return;
        lastSent = t;
        sendFrame();
        return;
      }
      if (paused) {
        // Throttle paused inference (was Δt>40ms → flood during scrub settle)
        if (t - lastPausedSendAt.current < YOLO_PAUSED_THROTTLE_MS) return;
        // Count attempts, not only successful sends, so a suspended Viewer does
        // not emit a skip log on every RAF.
        lastPausedSendAt.current = t;
        const tSec = videoRef.current?.currentTime ?? 0;
        if (
          Math.abs(tSec - lastPausedAt.current) < 0.04 &&
          lastPausedAt.current >= 0 &&
          !inFlightRef.current
        ) {
          return;
        }
        if (sendFrame()) {
          lastPausedAt.current = tSec;
        }
        return;
      }
      if (t - lastSent < (1000 / 30) * step) return;
      lastSent = t;
      sendFrame();
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [
    yoloAlwaysOn,
    isLive,
    analysisConfig,
    paused,
    editMode,
    seekEpoch,
    viewer?.sourcePath,
  ]);

  useEffect(() => {
    if (isLive && overlayMode === 'seg') setOverlayMode('detect');
  }, [isLive, overlayMode]);

  useEffect(() => {
    const prev = overlayModeRef.current;
    overlayModeRef.current = overlayMode;
    if (prev !== 'seg' || overlayMode !== 'detect' || !isAuthenticated) return;
    void fetch('/api/seg/unload', { method: 'POST', headers: authHeaders() })
      .then(() => {
        setSegLoaded(false);
      })
      .catch(() => {
        /* ignore */
      });
    void unloadSam3();
  }, [overlayMode, isAuthenticated, unloadSam3]);

  useEffect(() => {
    if (overlayMode !== 'seg') {
      // Live freeze SAM keeps temporary masks on detect overlay until play.
      if (!isLive) {
        setSegMasks([]);
        setInferN(0);
        setInferKind('—');
      }
      setSegBusy(false);
      setSamTool('none');
      return;
    }
    if (!isAuthenticated) return;
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch('/api/seg/status', { headers: authHeaders() });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          ready?: boolean;
          loaded?: boolean;
          weight?: string | null;
        };
        if (cancelled) return;
        const ready = Boolean(data.ready);
        const loaded = Boolean(data.loaded);
        setSegReady(ready);
        setSegLoaded(loaded);
        if (!ready) {
          setSegHint('Нет yolo26n-seg.pt — детекция работает');
        } else if (!loaded) {
          setSegHint('загрузите модель (Система)');
        } else {
          setSegHint(data.weight || 'yolo26-seg');
        }
      } catch {
        if (!cancelled) {
          setSegReady(false);
          setSegLoaded(false);
          setSegHint('Нет yolo26n-seg.pt — детекция работает');
        }
      }
      if (!cancelled) await refreshSamStatus();
    })();
    return () => {
      cancelled = true;
    };
  }, [overlayMode, isAuthenticated, refreshSamStatus, setSamTool, isLive]);

  // Live: keep SAM status fresh without entering archive SEG mode.
  useEffect(() => {
    if (!isLive || !isAuthenticated) return;
    void refreshSamStatus();
  }, [isLive, isAuthenticated, refreshSamStatus]);

  const runSegFrame = useCallback(async () => {
    if (overlayMode !== 'seg' || isLive || !segLoaded) return;
    const video = videoRef.current;
    if (!video || video.readyState < 2 || video.videoWidth <= 0) return;
    if (video.seeking || pendingSeekTime.current != null) return;
    const jpeg = captureFrame(video);
    if (!jpeg) return;
    const gen = ++segGenRef.current;
    setSegBusy(true);
    try {
      const res = await fetch('/api/seg/infer', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          image_base64: jpeg,
          confidence: analysisConfig.confidenceThreshold,
        }),
      });
      if (segGenRef.current !== gen) return;
      if (res.status === 503) {
        const body = (await res.json().catch(() => ({}))) as { detail?: string };
        const detail = typeof body.detail === 'string' ? body.detail : '';
        if (detail.includes('VRAM') || detail.includes('не в VRAM')) {
          setSegLoaded(false);
          setSegHint('загрузите модель (Система)');
        } else {
          setSegReady(false);
          setSegLoaded(false);
          setSegHint('Нет yolo26n-seg.pt — детекция работает');
        }
        setSegMasks([]);
        return;
      }
      if (!res.ok) return;
      const data = (await res.json()) as {
        masks?: SegMask[];
        ms?: number;
        weight?: string;
      };
      if (segGenRef.current !== gen) return;
      const masks = Array.isArray(data.masks) ? data.masks : [];
      setSegMasks(masks);
      setInferN(masks.length);
      setInferMs(typeof data.ms === 'number' ? data.ms : 0);
      setInferKind(data.weight || 'seg');
      setYoloHud('ready');
    } catch {
      /* network */
    } finally {
      if (segGenRef.current === gen) setSegBusy(false);
    }
  }, [
    overlayMode,
    isLive,
    segLoaded,
    analysisConfig.confidenceThreshold,
  ]);

  const unloadSegModel = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      await fetch('/api/seg/unload', { method: 'POST', headers: authHeaders() });
    } catch {
      /* ignore */
    }
    setSegLoaded(false);
    setSegHint(segReady ? 'загрузите модель (Система)' : 'Нет yolo26n-seg.pt — детекция работает');
  }, [isAuthenticated, segReady]);

  const loadSegModel = useCallback(async () => {
    if (!isAuthenticated || !segReady) return;
    setSegBusy(true);
    try {
      const res = await fetch('/api/seg/load', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({}),
      });
      const data = (await res.json().catch(() => ({}))) as {
        loaded?: boolean;
        weight?: string;
        detail?: string;
        sam_unloaded?: boolean;
      };
      if (!res.ok) {
        setSegHint(typeof data.detail === 'string' ? data.detail : 'загрузите модель (Система)');
        setSegLoaded(false);
        return;
      }
      setSegLoaded(Boolean(data.loaded) || true);
      setSegHint(data.weight || 'yolo26-seg');
      markSamUnloadedByYolo();
    } catch {
      setSegHint('загрузите модель (Система)');
    } finally {
      setSegBusy(false);
    }
  }, [isAuthenticated, segReady, markSamUnloadedByYolo]);

  const onLoadSam3 = useCallback(async () => {
    if (!isAuthenticated || !samReady) return;
    await loadSam3();
    if (useSam3Store.getState().loaded) {
      setSegLoaded(false);
      setSegHint(segReady ? 'загрузите модель (Система)' : 'Нет yolo26n-seg.pt — детекция работает');
    }
  }, [isAuthenticated, samReady, loadSam3, segReady]);

  const runSamPoint = useCallback(
    async (e: React.PointerEvent) => {
      if (!samLoaded || samBusy) return;
      const svg = svgRef.current;
      if (!svg) return;
      const video = videoRef.current;
      const effectivelyPaused = video ? video.paused : paused;
      if (!effectivelyPaused) {
        setSamHint('Для точки SAM3 поставьте видео на паузу');
        return;
      }
      if (!paused) setPaused(true);
      const r = svg.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const p = {
        x: clamp01((e.clientX - r.left) / r.width),
        y: clamp01((e.clientY - r.top) / r.height),
      };
      e.stopPropagation();
      e.preventDefault();
      let jpeg = video ? captureFrame(video) : undefined;
      if (!jpeg && video && video.videoWidth > 0 && video.videoHeight > 0) {
        // Fallback: blank JPEG of declared size (decode not ready yet)
        const c = document.createElement('canvas');
        c.width = Math.min(64, video.videoWidth);
        c.height = Math.min(64, video.videoHeight);
        c.getContext('2d')?.fillRect(0, 0, c.width, c.height);
        jpeg = c.toDataURL('image/jpeg', 0.7);
      }
      if (!jpeg) {
        setSamHint('Не удалось захватить кадр');
        return;
      }
      const label = e.shiftKey ? 0 : 1;
      try {
        const masks = await inferSam3({
          imageBase64: jpeg,
          points: [{ x: p.x, y: p.y, label }],
        });
        setSegMasks(masks);
        setInferN(masks.length);
        setInferKind('sam3');
        setSamHint(useSam3Store.getState().weight || 'sam3');
      } catch (err) {
        setSamHint(err instanceof Error ? err.message : 'Ошибка сегментации SAM3');
      }
    },
    [samLoaded, samBusy, paused, inferSam3, setSamHint],
  );

  const runSamFromDetection = useCallback(async () => {
    if (!samLoaded || samBusy || !paused || !activeDetectionId) return;
    const obj =
      overlayObjects.find((o) => o.id === activeDetectionId) ||
      liveObjects.find((o) => o.id === activeDetectionId);
    if (!obj?.bbox) return;
    const video = videoRef.current;
    const jpeg = video ? captureFrame(video) : undefined;
    if (!jpeg) return;
    const { x1, y1, x2, y2 } = obj.bbox;
    try {
      const masks = await inferSam3({
        imageBase64: jpeg,
        bboxes: [{ x1, y1, x2, y2 }],
      });
      setSegMasks(masks);
      setInferN(masks.length);
      setInferKind('sam3');
    } catch {
      /* ignore */
    }
  }, [
    samLoaded,
    samBusy,
    paused,
    activeDetectionId,
    overlayObjects,
    liveObjects,
    inferSam3,
  ]);

  const runSamText = useCallback(async () => {
    if (!samLoaded || samBusy) return;
    const texts = parseSam3TextPrompt(samTextPrompt);
    if (!texts.length) return;
    // Archive: require pause. Live freeze-frame does not require pause.
    if (!isLive && !paused) return;
    const video = videoRef.current;
    const jpeg = video ? captureFrame(video) : undefined;
    if (!jpeg) return;
    try {
      const masks = await inferSam3({ imageBase64: jpeg, text: texts });
      setSegMasks(masks);
      setInferN(masks.length);
      setInferKind('sam3');
    } catch {
      /* network / 503 */
    }
  }, [samLoaded, samBusy, samTextPrompt, isLive, paused, inferSam3]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.playbackRate = playbackRate;
  }, [playbackRate, viewer?.sourcePath]);

  useEffect(() => {
    if (!cdSeekTargets || !compareMode) return;
    const target =
      viewerId === 'viewer-1'
        ? cdSeekTargets['viewer-1']
        : viewerId === 'viewer-2'
          ? cdSeekTargets['viewer-2']
          : null;
    if (target == null || !Number.isFinite(target)) return;
    const video = videoRef.current;
    applyVideoSeek(target, { force: true, useFastSeek: false });
    if (video && !video.paused) video.pause();
    setPlaying(viewerId, false);
    if (viewerId === 'viewer-1') {
      setPlayheadPosition(target);
    }
  }, [cdSeekTargets?.epoch, compareMode, viewerId]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onSeeked = () => {
      settleSeek(video);
    };
    video.addEventListener('seeked', onSeeked);
    return () => video.removeEventListener('seeked', onSeeked);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewer?.sourcePath, isPrimaryDriver, setPreviewFrame]);

  useEffect(() => {
    ignoreSeek.current = false;
    pendingSeekTime.current = null;
    setSeekInFlight(false);
    setLiveObjects([]);
    setFrozenLive([]);
    setLiveStamp(-1);
    setSegMasks([]);
    freezeTimeRef.current = -1;
    lastPausedAt.current = -1;
    remountGuardUntil.current = performance.now() + REMOUNT_PUBLISH_GUARD_MS;
    const path = viewer?.sourcePath ?? '';
    const cached = viewerTimeCache.get(viewerId);
    if (cached && path && cached.path !== path) {
      viewerTimeCache.delete(viewerId);
      lastKnownTime.current = 0;
    } else if (cached?.path === path) {
      lastKnownTime.current = cached.t;
    }
    if (viewerId === 'viewer-1') {
      useTimelineStore.getState().clearLiveMarks();
    }
  }, [viewer?.sourcePath, viewerId]);

  // Persist lastKnownTime across mosaic unmount/remount
  useEffect(() => {
    const path = viewer?.sourcePath;
    remountGuardUntil.current = performance.now() + REMOUNT_PUBLISH_GUARD_MS;
    return () => {
      const video = videoRef.current;
      const t =
        video && Number.isFinite(video.currentTime) && video.currentTime > 0
          ? video.currentTime
          : lastKnownTime.current > 0
            ? lastKnownTime.current
            : useTimelineStore.getState().playheadPosition;
      if (path && t > 0) {
        rememberViewerTime(viewerId, path, t);
        lastKnownTime.current = t;
      }
    };
  }, [viewerId, viewer?.sourcePath]);

  useEffect(() => {
    ignoreSeek.current = false;
  }, [compareMode, syncMode]);

  // Compare Sync: when follow engages, slave snaps once via seek path (ongoing: subscribe+seekEpoch)
  useEffect(() => {
    if (!isCompareSyncSlave) return;
    const target =
      useTimelineStore.getState().playheadPosition + syncOffsetRef.current;
    remountGuardUntil.current = performance.now() + REMOUNT_PUBLISH_GUARD_MS;
    const ok = applyVideoSeek(target, { force: true });
    if (!ok) {
      const retry = window.setTimeout(() => {
        applyVideoSeek(useTimelineStore.getState().playheadPosition + syncOffsetRef.current, {
          force: true,
        });
      }, 40);
      return () => window.clearTimeout(retry);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCompareSyncSlave, syncMode]);

  // Compare Sync slave: correct play drift without publishing playhead
  useEffect(() => {
    if (!isCompareSyncSlave || playbackState !== 'playing') return;
    const id = window.setInterval(() => {
      const video = videoRef.current;
      if (!video || video.readyState < 1) return;
      if (video.seeking || pendingSeekTime.current != null) return;
      const target =
        useTimelineStore.getState().playheadPosition + syncOffsetRef.current;
      if (Math.abs(video.currentTime - target) > 0.35) {
        applyVideoSeek(target, { force: true, useFastSeek: true });
      }
    }, 500);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isCompareSyncSlave, playbackState]);

  // pendingJump safety: clear even if applyVideoSeek fails (source never loads)
  const pendingJump = useTimelineStore((s) => s.pendingJump);
  useEffect(() => {
    if (pendingJump == null) return;
    if (!isPrimaryDriver && !shouldSyncToPlayhead) return;
    const timer = window.setTimeout(() => {
      if (useTimelineStore.getState().pendingJump != null) {
        useTimelineStore.getState().setPendingJump(null);
      }
    }, 5000);
    const video = videoRef.current;
    if (video && video.readyState >= 1) {
      try {
        const target = isCompareSyncSlave
          ? pendingJump + syncOffsetRef.current
          : pendingJump;
        applyVideoSeek(target, { force: true });
      } finally {
        useTimelineStore.getState().setPendingJump(null);
      }
    }
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingJump, isPrimaryDriver, shouldSyncToPlayhead, isCompareSyncSlave]);

  // Single path: scrub OR discrete seekEpoch — never seek on clock playhead updates
  useEffect(() => {
    if (!shouldSyncToPlayhead) return;
    let raf = 0;
    let scrubPending = -1;
    let retryTimer = 0;
    let discreteDebounce = 0;

    const unsub = useTimelineStore.subscribe(
      (s) => ({ pos: s.playheadPosition, scrubbing: s.isScrubbing, epoch: s.seekEpoch }),
      (curr, prev) => {
        if (
          curr.pos === prev.pos &&
          curr.scrubbing === prev.scrubbing &&
          curr.epoch === prev.epoch
        ) {
          return;
        }
        if (curr.scrubbing) {
          if (discreteDebounce) {
            window.clearTimeout(discreteDebounce);
            discreteDebounce = 0;
          }
          scrubPending = curr.pos;
          if (!raf) {
            raf = requestAnimationFrame(() => {
              raf = 0;
              if (scrubPending >= 0) {
                applyVideoSeek(scrubPending, { force: true, useFastSeek: true });
              }
              scrubPending = -1;
            });
          }
          return;
        }
        // Discrete seek only when seekEpoch bumps (Inspector / markers / seekTo / Sync)
        if (curr.epoch === prev.epoch) {
          return;
        }
        // Close the debounce window immediately: no stale frame may leave while
        // the discrete click/jump waits for its coalesced seek.
        if (!isLive) armYoloSuspend();
        const offset =
          compareMode &&
          (useTimelineStore.getState().syncMode === 'follow' || syncPlayhead) &&
          focusedViewerId !== viewerId
            ? syncOffsetRef.current
            : 0;
        if (discreteDebounce) window.clearTimeout(discreteDebounce);
        discreteDebounce = window.setTimeout(() => {
          discreteDebounce = 0;
          const ok = applyVideoSeek(curr.pos + offset, { force: true, useFastSeek: false });
          if (!ok) {
            seekRetryRef.current = 0;
            const retry = () => {
              seekRetryRef.current += 1;
              const applied = applyVideoSeek(
                useTimelineStore.getState().playheadPosition + offset,
                { force: true },
              );
              if (!applied && seekRetryRef.current < 40) {
                retryTimer = window.setTimeout(retry, 50);
              }
            };
            retryTimer = window.setTimeout(retry, 40);
          }
        }, DISCRETE_SEEK_DEBOUNCE_MS);
      },
      {
        equalityFn: (a, b) =>
          a.pos === b.pos && a.scrubbing === b.scrubbing && a.epoch === b.epoch,
        fireImmediately: false,
      },
    );

    return () => {
      unsub();
      if (raf) cancelAnimationFrame(raf);
      if (retryTimer) window.clearTimeout(retryTimer);
      if (discreteDebounce) window.clearTimeout(discreteDebounce);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldSyncToPlayhead]);

  useEffect(() => {
    if (!shouldSyncToPlayhead) return;
    const video = videoRef.current;
    if (!video) return;
    if (playbackState === 'playing' && video.paused && pendingSeekTime.current == null) {
      void video.play().catch(() => undefined);
    } else if (playbackState !== 'playing' && !video.paused) {
      video.pause();
    }
  }, [playbackState, shouldSyncToPlayhead]);

  const togglePlayPause = () => {
    const video = videoRef.current;
    if (!video) return;
    if (!video.paused) {
      video.pause();
      return;
    }
    setEditMode(false);
    setFrozenLive([]);
    void video.play().catch(() => undefined);
  };

  const toggleRec = async () => {
    if (recBusy) return;
    setRecBusy(true);
    try {
      if (recOn) {
        const res = await fetch('/api/rec/stop', {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({ drone_id: viewerId }),
        });
        if (!res.ok) throw new Error('REC stop failed');
        setRecOn(false);
        setRecStartedAt(null);
        setRecElapsed(0);
      } else {
        if (!viewer?.sourcePath) throw new Error('Нет источника для записи');
        const res = await fetch('/api/rec/start', {
          method: 'POST',
          headers: authHeaders(),
          body: JSON.stringify({
            drone_id: viewerId,
            source_path: viewer.sourcePath,
            start_sec: videoRef.current?.currentTime ?? 0,
          }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(typeof data.detail === 'string' ? data.detail : 'REC start failed');
        }
        setRecOn(true);
        setRecStartedAt(Date.now());
        setRecElapsed(0);
      }
    } catch (err) {
      console.error(err);
      setStatus(err instanceof Error ? err.message : 'REC error');
    } finally {
      setRecBusy(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) return;
    let cancelled = false;
    const poll = () => {
      void fetch(`/api/rec/status?drone_id=${encodeURIComponent(viewerId)}`, { headers: authHeaders() })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (cancelled || !data) return;
          const on = Boolean(data.recording);
          setRecOn(on);
          if (on && typeof data.started_at === 'number') {
            setRecStartedAt(data.started_at * 1000);
          } else if (!on) {
            setRecStartedAt(null);
            setRecElapsed(0);
          }
        })
        .catch(() => undefined);
    };
    poll();
    const id = window.setInterval(poll, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [isAuthenticated, viewerId]);

  useEffect(() => {
    if (!recOn || recStartedAt == null) return;
    const tick = () => setRecElapsed(Math.max(0, Math.floor((Date.now() - recStartedAt) / 1000)));
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [recOn, recStartedAt]);

  const enterEdit = () => {
    const video = videoRef.current;
    video?.pause();
    freezeTimeRef.current = video?.currentTime ?? timeSec;
    setFrozenLive(liveRef.current);
    setEditMode(true);
    setViewTool('select');
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  const removeActiveBox = () => {
    const obj =
      overlayObjects.find((o) => o.id === activeDetectionId) ||
      liveObjects.find((o) => o.id === activeDetectionId);
    if (!obj) return;
    setLiveObjects((prev) => prev.filter((o) => o.id !== obj.id));
    setFrozenLive((prev) => prev.filter((o) => o.id !== obj.id));
    void dismissDetection(obj, sourceVideo, timeSec);
  };

  const onPause = () => {
    setPaused(true);
    setPlaying(viewerId, false);
    setFrozenLive(liveRef.current);
    if (canPublishPlayhead) timelinePause();
  };

  const onPlay = () => {
    setPaused(false);
    setPlaying(viewerId, true);
    if (editMode) setEditMode(false);
    setFrozenLive([]);
    // Live freeze SAM overlay must not stick on a moving stream.
    if (isLive || overlayMode === 'seg') {
      setSegMasks([]);
      setInferN(0);
      setInferKind('—');
    }
    if (canPublishPlayhead) timelinePlay();
  };

  const freezeFrame = async () => {
    const video = videoRef.current;
    const objects = commitableLive;
    if (!objects.length || committing) return;
    setCommitting(true);
    try {
      const jpeg = video ? captureFrame(video) : undefined;
      await commitFrame({
        source_video: sourceVideo,
        time_sec: video?.currentTime ?? timeSec,
        frame_idx: frameRef.current,
        frame_jpeg: jpeg,
        objects: objects.map((o) => ({
          class_id: o.class_id ?? 0,
          class_name: o.class_en || o.class_ru,
          confidence: o.confidence,
          bbox: o.bbox,
        })),
      });
      setFrozenLive([]);
    } finally {
      setCommitting(false);
    }
  };

  // Global F / Ctrl+S hotkey (src/hooks/useHotkeys.ts) requests a freeze-frame
  // for the focused viewer via this CustomEvent.
  useEffect(() => {
    const onFreeze = (e: Event) => {
      const detail = (e as CustomEvent).detail as { viewerId?: string } | undefined;
      if (detail?.viewerId !== viewerId) return;
      void freezeFrame();
    };
    window.addEventListener('muravei:freeze-frame', onFreeze as EventListener);
    return () => window.removeEventListener('muravei:freeze-frame', onFreeze as EventListener);
  }, [freezeFrame]);

  const pointerNorm = (e: React.PointerEvent): { x: number; y: number } | null => {
    const svg = svgRef.current;
    if (!svg) return null;
    const r = svg.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return {
      x: clamp01((e.clientX - r.left) / r.width),
      y: clamp01((e.clientY - r.top) / r.height),
    };
  };

  const onOverlayPointerDown = (e: React.PointerEvent, id: string | null, handle: HandleKey) => {
    if (viewTool === 'pan') return;
    if (!editMode) {
      if (id) {
        const obj = overlayObjects.find((o) => o.id === id);
        if (obj) setActiveDetection(obj);
      }
      return;
    }
    e.stopPropagation();
    const p = pointerNorm(e);
    if (!p) return;
    svgRef.current?.setPointerCapture(e.pointerId);
    if (handle === 'draw') {
      dragRef.current = {
        handle: 'draw',
        id: null,
        start: { x1: p.x, y1: p.y, x2: p.x, y2: p.y },
        originX: p.x,
        originY: p.y,
        persisted: false,
      };
      setDraft({ x1: p.x, y1: p.y, x2: p.x, y2: p.y });
      return;
    }
    const obj = overlayObjects.find((o) => o.id === id);
    if (!obj) return;
    setActiveDetection(obj);
    dragRef.current = {
      handle,
      id: obj.id,
      start: { ...obj.bbox },
      originX: p.x,
      originY: p.y,
      persisted: detections.some((d) => d.id === obj.id),
    };
  };

  const onOverlayPointerMove = (e: React.PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    const p = pointerNorm(e);
    if (!p) return;
    if (drag.handle === 'draw') {
      setDraft({
        x1: Math.min(drag.originX, p.x),
        y1: Math.min(drag.originY, p.y),
        x2: Math.max(drag.originX, p.x),
        y2: Math.max(drag.originY, p.y),
      });
      return;
    }
    const next = applyHandle(drag.start, drag.handle, p.x, p.y, p.x - drag.originX, p.y - drag.originY);
    if (drag.id) {
      const preview = { id: drag.id, bbox: next };
      dragPreviewRef.current = preview;
      setDragPreview(preview);
    }
    if (!drag.persisted) {
      setFrozenLive((prev) => prev.map((o) => (o.id === drag.id ? { ...o, bbox: next } : o)));
      setLiveObjects((prev) => prev.map((o) => (o.id === drag.id ? { ...o, bbox: next } : o)));
    }
  };

  const onOverlayPointerUp = async (e: React.PointerEvent) => {
    const drag = dragRef.current;
    dragRef.current = null;
    const preview = dragPreviewRef.current;
    dragPreviewRef.current = null;
    setDragPreview(null);
    if (!drag) return;
    const video = videoRef.current;
    const jpeg = video ? captureFrame(video) : undefined;
    if (drag.handle === 'draw') {
      const box = draft ? normBox(draft) : null;
      setDraft(null);
      if (!box || box.x2 - box.x1 < MIN_BOX || box.y2 - box.y1 < MIN_BOX) return;
      const cls =
        classCatalog.find((item) => item.id === manualClassId && item.enabled !== false) ??
        classCatalog.find((item) => item.enabled !== false);
      if (!cls) return;
      await createDetection({
        source_video: sourceVideo,
        time_sec: video?.currentTime ?? timeSec,
        frame_idx: frameRef.current,
        class_id: cls?.id ?? 0,
        class_name: cls?.name_en,
        confidence: 1,
        bbox: box,
        origin: 'manual',
        frame_jpeg: jpeg,
      });
      return;
    }
    const finalBox = preview?.bbox ?? drag.start;
    if (drag.persisted && drag.id) {
      await patchDetection(drag.id, { bbox: finalBox }, jpeg);
    }
    void e;
  };

  const mediaSrc =
    viewer?.sourceUrl ||
    (viewer?.sourcePath
      ? `/api/media/stream?path=${encodeURIComponent(viewer.sourcePath)}&token=${encodeURIComponent(authToken())}`
      : undefined);
  const liveMjpegSrc =
    isLive
      ? `/api/live/${encodeURIComponent(viewerId)}/mjpeg?token=${encodeURIComponent(authToken())}`
      : undefined;
  const hasMedia = Boolean(
    isLive ||
      viewer?.sourceUrl ||
      (viewer?.sourcePath && /\.(mp4|webm|mov|avi|mkv)$/i.test(viewer.sourcePath)),
  );

  const startLive = async () => {
    const url = (liveDraft || viewer?.liveUrl || '').trim();
    if (!url) {
      setLiveError('Укажите RTSP/UDP/HTTP URL');
      return;
    }
    setLiveBusy(true);
    setLiveError(null);
    try {
      const res = await fetch('/api/live/open', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ viewer_id: viewerId, url }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'live open failed');
      setLiveUrl(viewerId, url);
      setLiveActive(viewerId, true);
      setSourceMode(viewerId, 'live');
      setPaused(false);
      logger.info('yolo', `${viewerId}: live open ${url}`);
    } catch (e) {
      setLiveError(String(e));
      setLiveActive(viewerId, false);
    } finally {
      setLiveBusy(false);
    }
  };

  const stopLive = async () => {
    setLiveBusy(true);
    try {
      await fetch(`/api/live/${encodeURIComponent(viewerId)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      });
    } catch {
      /* ignore */
    } finally {
      setLiveActive(viewerId, false);
      setLiveBusy(false);
      setPaused(true);
      logger.info('yolo', `${viewerId}: live closed`);
    }
  };
  const freezeDisabled =
    committing || (!paused && !editMode) || commitableLive.length === 0;

  return (
    <div
      data-testid={viewerId}
      className={`relative h-full w-full flex flex-col bg-dv-deep outline-none ${
        focusedViewerId === viewerId ? 'ring-1 ring-dv-accent/50' : ''
      }`}
      tabIndex={0}
      onPointerDownCapture={() => setFocusedViewer(viewerId)}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const path = e.dataTransfer.getData('text/plain');
        if (path) setSource(viewerId, path, null);
      }}
    >
      <YoloDebugOverlay />
      <div
        ref={toolbarRef}
        className="flex items-center gap-0 px-1.5 py-1 border-b border-dv-border text-[10px] text-dv-muted flex-nowrap overflow-hidden min-h-[32px]"
      >
        <ToolbarGroup>
          <Button
            size="sm"
            active={!paused && !editMode}
            onClick={togglePlayPause}
          >
            {!paused && !editMode ? <Pause size={11} /> : <Play size={11} />}
            {!paused && !editMode ? 'Пауза' : 'Пуск'}
          </Button>
          <Button size="sm" active={editMode} onClick={enterEdit}>
            <Pencil size={11} />
            Правка
          </Button>
          {editMode && (
            <select
              aria-label="Класс ручной рамки"
              className="max-w-36 bg-dv-deep border border-dv-border px-1 py-0.5 text-[10px] text-dv-text"
              value={manualClassId ?? ''}
              onChange={(event) => setManualClassId(Number(event.target.value))}
            >
              {classCatalog
                .filter((item) => item.enabled !== false)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} · {item.name_ru || item.name_en}
                  </option>
                ))}
            </select>
          )}
        </ToolbarGroup>

        <ToolbarGroup>
          <IconButton
            label="Указатель"
            active={viewTool === 'select'}
            onClick={() => setViewTool('select')}
          >
            <MousePointer2 size={11} />
          </IconButton>
          <IconButton
            label="Панорама"
            active={viewTool === 'pan'}
            onClick={() => setViewTool('pan')}
          >
            <Hand size={11} />
          </IconButton>
          <IconButton
            label="Увеличить"
            onClick={() => {
              setZoom((z) => Math.min(8, Number((z * 1.25).toFixed(2))));
              setViewTool('pan');
            }}
          >
            <ZoomIn size={11} />
          </IconButton>
          <IconButton
            label="Уменьшить"
            onClick={() => {
              setZoom((z) => Math.max(1, Number((z / 1.25).toFixed(2))));
              setViewTool('pan');
            }}
          >
            <ZoomOut size={11} />
          </IconButton>
          <IconButton label="Вписать" onClick={resetView}>
            <Maximize2 size={11} />
          </IconButton>
          <span className="font-mono text-[9px] w-7 text-center">{zoom.toFixed(1)}×</span>
        </ToolbarGroup>

        <ToolbarGroup>
          <Button
            size="sm"
            active={!isLive && (viewer?.sourceMode ?? 'archive') === 'archive'}
            onClick={() => {
              if (isLive) void stopLive();
              setSourceMode(viewerId, 'archive');
            }}
          >
            Архив
          </Button>
          <Button
            size="sm"
            active={isLive || viewer?.sourceMode === 'live'}
            onClick={() => {
              setOverlayMode('detect');
              setSourceMode(viewerId, 'live');
            }}
          >
            Live
          </Button>
        </ToolbarGroup>

        {!isLive && (viewer?.sourceMode ?? 'archive') === 'archive' && (
          <ToolbarGroup>
            <Button
              size="sm"
              active={overlayMode === 'detect'}
              onClick={() => setOverlayMode('detect')}
              title="YOLO-детекция (bbox)"
            >
              Детекция
            </Button>
            <Button
              size="sm"
              active={overlayMode === 'seg'}
              disabled={!isAuthenticated}
              onClick={() => setOverlayMode('seg')}
              title="Сегментация текущего кадра (архив). Не пишет в обучение."
            >
              Сегментация
            </Button>
            {overlayMode === 'seg' && (
              <>
                {segReady && !segLoaded && (
                  <Button
                    size="sm"
                    disabled={!isAuthenticated || segBusy}
                    onClick={() => void loadSegModel()}
                    title="Загрузить yolo26n/s-seg в VRAM"
                  >
                    {segBusy ? 'загрузка…' : 'Загрузить'}
                  </Button>
                )}
                <Button
                  size="sm"
                  disabled={
                    !isAuthenticated ||
                    !segLoaded ||
                    !paused ||
                    segBusy ||
                    seekInFlight
                  }
                  onClick={() => void runSegFrame()}
                  title={
                    !segReady
                      ? 'Нет yolo26n-seg.pt — детекция работает'
                      : !segLoaded
                        ? 'загрузите модель (Система)'
                        : paused
                          ? 'Сегментировать текущий кадр'
                          : 'Поставьте на паузу'
                  }
                >
                  {segBusy ? 'сег…' : 'Сегментировать кадр'}
                </Button>
                <Button
                  size="sm"
                  disabled={
                    !isAuthenticated ||
                    !segLoaded ||
                    !viewer?.sourcePath ||
                    segBusy ||
                    isLive
                  }
                  onClick={() => setBatchSegOpen(true)}
                  title="Пакетная сегментация ролика (шаг кадров)"
                >
                  Batch сегментация
                </Button>
                <Button
                  size="sm"
                  disabled={!isAuthenticated || !segLoaded || segBusy}
                  onClick={() => void unloadSegModel()}
                  title="Выгрузить seg-модель из VRAM"
                >
                  Выгрузить
                </Button>
                <span
                  className={`text-[9px] font-mono max-w-[160px] truncate ${
                    segLoaded ? 'text-dv-muted' : 'text-dv-danger'
                  }`}
                  title={segHint || ''}
                >
                  {segHint || (segReady ? 'seg' : 'нет весов')}
                </span>
                {samReady && !samLoaded && (
                  <Button
                    size="sm"
                    disabled={!isAuthenticated || samBusy || segBusy}
                    onClick={() => void onLoadSam3()}
                    title="Загрузить SAM3 (выгрузит YOLO-seg)"
                    data-testid="sam3-load"
                  >
                    {samBusy ? 'SAM…' : 'Загрузить SAM3'}
                  </Button>
                )}
                {samLoaded && (
                  <>
                    <Button
                      size="sm"
                      active={samTool === 'point'}
                      disabled={!isAuthenticated || samBusy}
                      onClick={() => setSamTool(samTool === 'point' ? 'none' : 'point')}
                      title="Точка: ЛКМ — объект, Shift+ЛКМ — фон. Пауза."
                      data-testid="sam3-tool-point"
                    >
                      Точка
                    </Button>
                    <Button
                      size="sm"
                      disabled={
                        !isAuthenticated ||
                        samBusy ||
                        !paused ||
                        !activeDetectionId
                      }
                      onClick={() => void runSamFromDetection()}
                      title="Маска SAM3 по bbox активной детекции"
                      data-testid="sam3-from-detection"
                    >
                      SAM из детекции
                    </Button>
                    <input
                      className="bg-dv-deep border border-dv-border px-1 py-0.5 text-[9px] font-mono w-[160px] max-w-[28vw]"
                      placeholder="trench / окоп; person; vehicle"
                      value={samTextPrompt}
                      onChange={(e) => setSamTextPrompt(e.target.value)}
                      disabled={!isAuthenticated || samBusy}
                      title="Текстовые промпты через ; (1–3)"
                      data-testid="sam3-text-input"
                    />
                    <Button
                      size="sm"
                      disabled={
                        !isAuthenticated ||
                        samBusy ||
                        !parseSam3TextPrompt(samTextPrompt).length ||
                        (!isLive && !paused)
                      }
                      onClick={() => void runSamText()}
                      title={
                        isLive
                          ? 'Freeze-кадр SAM по тексту (detect не останавливается)'
                          : 'Маска SAM3 по тексту (нужна пауза)'
                      }
                      data-testid={isLive ? 'sam3-live-frame' : 'sam3-text-infer'}
                    >
                      {isLive ? 'Кадр SAM' : 'По тексту'}
                    </Button>
                    <Button
                      size="sm"
                      disabled={
                        !isAuthenticated ||
                        samBusy ||
                        !paused ||
                        !viewer?.sourcePath ||
                        !hasSamSeed ||
                        isLive
                      }
                      onClick={() => setSamPropOpen(true)}
                      title="Пропагировать маску вперёд ≤30 кадров"
                      data-testid="sam3-propagate"
                    >
                      Пропагировать
                    </Button>
                    <Button
                      size="sm"
                      disabled={!isAuthenticated || samBusy}
                      onClick={() => void unloadSam3()}
                      title="Выгрузить SAM3 из VRAM"
                    >
                      Выгрузить SAM
                    </Button>
                  </>
                )}
                <span
                  className={`text-[9px] font-mono max-w-[120px] truncate ${
                    samLoaded ? 'text-dv-muted' : 'text-dv-danger'
                  }`}
                  title={samHint || ''}
                  data-testid="sam3-hint"
                >
                  {samHint || (samReady ? 'sam3' : '')}
                </span>
                {samNotice ? (
                  <span
                    className="text-[9px] text-dv-accent max-w-[180px] truncate"
                    title={samNotice}
                    data-testid="sam3-notice"
                    onClick={() => clearSamNotice()}
                  >
                    {samNotice}
                  </span>
                ) : null}
              </>
            )}
          </ToolbarGroup>
        )}

        {(viewer?.sourceMode === 'live' || isLive) && (
          <ToolbarGroup>
            <input
              className="bg-dv-deep border border-dv-border px-1 py-0.5 text-[9px] font-mono w-[140px] max-w-[22vw]"
              placeholder="rtsp://… udp://… http://…"
              value={liveDraft || viewer?.liveUrl || ''}
              onChange={(e) => setLiveDraft(e.target.value)}
              title="RTSP / UDP / MJPEG URL"
            />
            {!isLive ? (
              <Button size="sm" disabled={liveBusy || !isAuthenticated} onClick={() => void startLive()}>
                {liveBusy ? '…' : 'Открыть'}
              </Button>
            ) : (
              <Button size="sm" disabled={liveBusy} onClick={() => void stopLive()}>
                Стоп
              </Button>
            )}
            {liveError && (
              <span className="text-[9px] text-dv-danger max-w-[100px] truncate" title={liveError}>
                {liveError}
              </span>
            )}
          </ToolbarGroup>
        )}

        {isLive && isAuthenticated && (samReady || samLoaded) && (
          <ToolbarGroup>
            {samReady && !samLoaded && (
              <Button
                size="sm"
                disabled={samBusy}
                onClick={() => void onLoadSam3()}
                title="Загрузить SAM3 для freeze-кадра (YOLO-detect не выгружается)"
                data-testid="sam3-load"
              >
                {samBusy ? 'SAM…' : 'Загрузить SAM3'}
              </Button>
            )}
            {samLoaded && (
              <>
                <input
                  className="bg-dv-deep border border-dv-border px-1 py-0.5 text-[9px] font-mono w-[160px] max-w-[28vw]"
                  placeholder="trench / окоп; person; vehicle"
                  value={samTextPrompt}
                  onChange={(e) => setSamTextPrompt(e.target.value)}
                  disabled={samBusy}
                  title="Текстовые промпты через ; (1–3)"
                  data-testid="sam3-text-input"
                />
                <Button
                  size="sm"
                  disabled={samBusy || !parseSam3TextPrompt(samTextPrompt).length}
                  onClick={() => void runSamText()}
                  title="Freeze-кадр SAM по тексту (detect продолжает работать)"
                  data-testid="sam3-live-frame"
                >
                  {samBusy ? 'SAM…' : 'Кадр SAM'}
                </Button>
                {segMasks.length > 0 && (
                  <Button
                    size="sm"
                    disabled={samBusy}
                    onClick={() => {
                      setSegMasks([]);
                      setInferN(0);
                      setInferKind('—');
                    }}
                    title="Снять временный SAM overlay"
                    data-testid="sam3-live-clear"
                  >
                    Сброс SAM
                  </Button>
                )}
                <Button
                  size="sm"
                  disabled={samBusy}
                  onClick={() => void unloadSam3()}
                  title="Выгрузить SAM3 из VRAM"
                >
                  Выгрузить SAM
                </Button>
              </>
            )}
            <span
              className={`text-[9px] font-mono max-w-[100px] truncate ${
                samLoaded ? 'text-dv-muted' : 'text-dv-danger'
              }`}
              title={samHint || ''}
              data-testid="sam3-hint"
            >
              {samHint || (samReady ? 'sam3' : '')}
            </span>
          </ToolbarGroup>
        )}

        <ToolbarGroup>
          <Button
            size="sm"
            active={showMotion}
            onClick={() => setShowMotion(!showMotion)}
            title="Стрелки движения объектов (видны при воспроизведении, если YOLO передал vx/vy)"
          >
            Векторы
          </Button>
          {viewerId === 'viewer-1' && (
            <>
              <Button
                size="sm"
                active={compareMode}
                onClick={() => {
                  const next = !compareMode;
                  setCompareMode(next);
                  if (!next) {
                    setSyncPlayhead(false);
                    setSyncMode('off');
                    cdClear();
                  }
                }}
                title="Сравнение: окно 1 — «Было», окно 2 — «Стало». Загрузите два ролика."
              >
                Было/Стало
              </Button>
              {compareMode && (
                <Button
                  size="sm"
                  active={syncPlayhead || syncMode === 'follow'}
                  onClick={() => {
                    const next = !(syncPlayhead || syncMode === 'follow');
                    setSyncPlayhead(next);
                    setSyncMode(next ? 'follow' : 'off');
                    if (next) {
                      // Bump epoch so all followers take the unified seek path
                      const pos = useTimelineStore.getState().playheadPosition;
                      seekTo(pos);
                    }
                  }}
                  title="Синхронизировать seek/play между окнами Было и Стало"
                >
                  Sync
                </Button>
              )}
              {compareMode && (
                <Button
                  size="sm"
                  disabled={
                    !isAuthenticated ||
                    !useViewerStore.getState().viewers['viewer-1']?.sourcePath ||
                    !useViewerStore.getState().viewers['viewer-2']?.sourcePath
                  }
                  onClick={() => setSyncModalOpen(true)}
                  title="Автосинхронизация времени по GPS-трекам или детекциям"
                >
                  Синхронизировать
                </Button>
              )}
              {compareMode && (
                <Button
                  size="sm"
                  disabled={
                    cdLoading ||
                    !isAuthenticated ||
                    !useViewerStore.getState().viewers['viewer-1']?.sourcePath ||
                    !useViewerStore.getState().viewers['viewer-2']?.sourcePath
                  }
                  onClick={() => {
                    const v1 = useViewerStore.getState().viewers['viewer-1'];
                    const v2 = useViewerStore.getState().viewers['viewer-2'];
                    if (!v1?.sourcePath || !v2?.sourcePath) return;
                    const syncOn =
                      useViewerStore.getState().syncPlayhead ||
                      useTimelineStore.getState().syncMode === 'follow';
                    void cdRunAnalysis({
                      videoBefore: v1.sourcePath,
                      videoAfter: v2.sourcePath,
                      timeBefore: videoRef.current?.currentTime ?? getViewerPlaybackTime('viewer-1'),
                      timeAfter: getViewerPlaybackTime('viewer-2'),
                      timeWindowSec: syncOn ? 0.5 : 2.0,
                    });
                  }}
                  title="GPS-сопоставление детекций Было/Стало (+ ORB fallback)"
                >
                  {cdLoading ? 'Анализ…' : 'Анализ изменений'}
                </Button>
              )}
              {compareMode &&
                viewerId === 'viewer-1' &&
                Boolean(cdResult?.image_diff?.heatmap_b64) && (
                  <Button
                    size="sm"
                    active={showHeatmap}
                    onClick={() => setShowHeatmap(!showHeatmap)}
                    title="Тепловая карта изменений (ORB/diff)"
                  >
                    Теплокарта
                  </Button>
                )}
            </>
          )}
        </ToolbarGroup>

        <ToolbarGroup>
          <span
            className="inline-flex items-center gap-1.5 text-[9px] text-dv-muted max-w-[220px] truncate px-1"
            title={`${mode} · ${status} · ${inferKind}`}
          >
            <span
              className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                yoloHud === 'ready'
                  ? 'bg-emerald-400'
                  : yoloHud === 'error'
                    ? 'bg-dv-danger'
                    : 'bg-amber-400'
              }`}
            />
            <Crosshair size={10} className="flex-shrink-0 text-dv-accent" />
            <span className="font-mono truncate">
              {overlayMode === 'seg'
                ? `SEG · ${inferKind} · ${inferN} · ${inferMs}ms`
                : `YOLO26 · ${inferKind} · ${inferN} obj · ${inferMs}ms`}
            </span>
          </span>
        </ToolbarGroup>

        {!toolbarNarrow && (
          <ToolbarGroup>
            <Button
              size="sm"
              disabled={recBusy || (!recOn && !viewer?.sourcePath)}
              className={recOn ? '!bg-dv-danger !text-white font-bold' : '!text-dv-danger'}
              title={recOn ? 'Остановить запись' : 'Запись в archive/recordings'}
              onClick={() => void toggleRec()}
            >
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  recOn ? 'bg-white animate-pulse' : 'bg-dv-danger'
                }`}
              />
              REC
              {recOn && (
                <span className="font-mono text-[10px] tabular-nums">
                  {String(Math.floor(recElapsed / 60)).padStart(2, '0')}:
                  {String(recElapsed % 60).padStart(2, '0')}
                </span>
              )}
            </Button>
            <Button
              size="sm"
              disabled={freezeDisabled}
              onClick={() => void freezeFrame()}
              title="Сохранить объекты кадра в SQLite"
            >
              <Camera size={11} />
              {committing ? 'Фиксация…' : 'Кадр'}
            </Button>
          </ToolbarGroup>
        )}

        {!toolbarNarrow && (
          <ToolbarGroup last>
            <Button
              size="sm"
              className="!text-dv-selection font-mono"
              onClick={() => markIn(videoRef.current?.currentTime)}
              title="In — начало (I)"
            >
              I
            </Button>
            <Button
              size="sm"
              className="!text-dv-danger font-mono"
              onClick={() => markOut(videoRef.current?.currentTime)}
              title="Out — конец (O)"
            >
              O
            </Button>
            <IconButton
              label="Удалить метку"
              disabled={!activeDetectionId}
              onClick={removeActiveBox}
            >
              <Trash2 size={11} />
            </IconButton>
          </ToolbarGroup>
        )}

        {toolbarNarrow && (
          <div className="relative shrink-0" onMouseDown={(e) => e.stopPropagation()}>
            <IconButton
              label="Ещё"
              active={toolbarMoreOpen}
              onClick={() => setToolbarMoreOpen((v) => !v)}
            >
              <MoreHorizontal size={12} />
            </IconButton>
            <Menu open={toolbarMoreOpen} className="w-48">
              <MenuItem
                disabled={recBusy || (!recOn && !viewer?.sourcePath)}
                onClick={() => {
                  void toggleRec();
                  setToolbarMoreOpen(false);
                }}
              >
                {recOn ? 'Стоп REC' : 'REC'}
              </MenuItem>
              <MenuItem
                disabled={freezeDisabled}
                onClick={() => {
                  void freezeFrame();
                  setToolbarMoreOpen(false);
                }}
              >
                Зафиксировать кадр
              </MenuItem>
              <MenuItem
                onClick={() => {
                  markIn(videoRef.current?.currentTime);
                  setToolbarMoreOpen(false);
                }}
              >
                Метка In (I)
              </MenuItem>
              <MenuItem
                onClick={() => {
                  markOut(videoRef.current?.currentTime);
                  setToolbarMoreOpen(false);
                }}
              >
                Метка Out (O)
              </MenuItem>
              <MenuItem
                disabled={!activeDetectionId}
                onClick={() => {
                  removeActiveBox();
                  setToolbarMoreOpen(false);
                }}
              >
                Удалить метку
              </MenuItem>
            </Menu>
          </div>
        )}

        <span className="truncate flex-1 text-right text-[9px] pl-2 min-w-0">
          {compareMode && viewerId === 'viewer-1' ? 'БЫЛО · ' : ''}
          {compareMode && viewerId === 'viewer-2' ? 'СТАЛО · ' : ''}
          {isLive
            ? `LIVE · ${viewer?.liveUrl || liveDraft || '—'}`
            : viewer?.sourcePath ?? 'Перетащите файл сюда'}
          {!editMode && paused ? ' · пауза' : editMode ? ' · правка' : ' · live'}
        </span>
      </div>
      {compareMode && viewerId === 'viewer-2' && (
        <div className="px-2 py-1 border-b border-dv-border text-[9px] text-dv-muted bg-dv-deep/80 flex flex-wrap gap-x-3 gap-y-0.5">
          {cdResult ? (
            <>
              <span className="text-dv-accent font-semibold">Изменения</span>
              <span title="новые">+ {cdResult.summary.new}</span>
              <span title="исчезли">− {cdResult.summary.removed}</span>
              <span title="перемещены">↔ {cdResult.summary.moved}</span>
              <span title="метод" className="font-mono opacity-80">
                {cdResult.method}
              </span>
              {cdResult.message ? (
                <span className="text-amber-400/90">{cdResult.message}</span>
              ) : null}
            </>
          ) : cdLoading ? (
            <span className="text-dv-accent">Анализ изменений…</span>
          ) : (
            <span>Нажмите «Анализ изменений» на viewer-1 (пауза на кадрах)</span>
          )}
        </div>
      )}
      <div
        ref={stageParentRef}
        className={`flex-1 relative min-h-0 flex items-center justify-center overflow-hidden ${
          viewTool === 'pan' ? 'cursor-grab' : ''
        }`}
        onPointerDown={(e) => {
          if (viewTool !== 'pan' && e.button !== 1) return;
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
          panDrag.current = { x: pan.x, y: pan.y, px: e.clientX, py: e.clientY };
        }}
        onPointerMove={(e) => {
          const drag = panDrag.current;
          if (!drag) return;
          setPan({ x: drag.x + (e.clientX - drag.px), y: drag.y + (e.clientY - drag.py) });
        }}
        onPointerUp={() => {
          panDrag.current = null;
        }}
        onPointerCancel={() => {
          panDrag.current = null;
        }}
      >
        {hasMedia ? (
          <>
          <div
            className="relative"
            style={{
              width: stage.w || '100%',
              height: stage.h || '100%',
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`,
              transformOrigin: 'center center',
            }}
          >
            {isLive ? (
              <img
                ref={liveImgRef}
                className="w-full h-full object-fill bg-black"
                src={liveMjpegSrc}
                alt="live"
                onLoad={() => layoutStage()}
              />
            ) : (
            <video
              ref={videoRef}
              className="w-full h-full object-fill"
              src={mediaSrc}
              controls={false}
              muted
              loop={inPoint == null && outPoint == null}
              onLoadedMetadata={(e) => {
                layoutStage();
                const dur = e.currentTarget.duration || 0;
                setLocalDuration(dur);
                if (focusedViewerId === viewerId) {
                  setMediaDuration(dur);
                }
                if (shouldSyncToPlayhead || isPrimaryDriver) {
                  restoreAfterMount();
                }
              }}
              onCanPlay={() => {
                if (!shouldSyncToPlayhead && !isPrimaryDriver) return;
                const video = videoRef.current;
                if (!video) return;
                const target = resolveRestoreTarget();
                if (Math.abs(video.currentTime - target) > TIME_TRUTH_DRIFT) {
                  remountGuardUntil.current = performance.now() + REMOUNT_PUBLISH_GUARD_MS;
                  applyVideoSeek(target, { force: true });
                }
              }}
              onLoadedData={() => {
                layoutStage();
                const video = videoRef.current;
                if (focusedViewerId === viewerId && video && pendingSeekTime.current == null) {
                  const thumb = captureThumb(video);
                  if (thumb) setPreviewFrame(thumb);
                }
              }}
              onPlay={onPlay}
              onPause={onPause}
              onTimeUpdate={(e) => {
                const video = e.currentTarget;
                const t = video.currentTime;
                // Block clock publish while seek/remount in flight; never clear pending here
                if (ignoreSeek.current || pendingSeekTime.current != null || video.seeking) {
                  return;
                }
                setTimeSec(t);
                lastKnownTime.current = t;
                rememberViewerTime(viewerId, viewer?.sourcePath, t);
                if (isPublishBlocked()) return;
                // Intention tracks reality during playback (primary only)
                setPlayheadPosition(t);
                const now = performance.now();
                if (now - lastPreviewAt.current > 200) {
                  lastPreviewAt.current = now;
                  const thumb = captureThumb(video);
                  if (thumb) setPreviewFrame(thumb);
                }
                if (outPoint != null && t >= outPoint) {
                  if (inPoint != null) {
                    applyVideoSeek(inPoint, { force: true });
                    if (!video.paused) void video.play().catch(() => undefined);
                  } else {
                    video.pause();
                    seekTo(outPoint);
                  }
                }
              }}
            />
            )}
            {compareMode && showHeatmap && cdResult?.image_diff?.heatmap_b64 ? (
              <HeatmapOverlay
                heatmapB64={cdResult.image_diff.heatmap_b64}
                opacity={0.5}
                visible
              />
            ) : null}
            <svg
              ref={svgRef}
              className={`absolute inset-0 w-full h-full ${
                overlayMode === 'seg'
                  ? samTool === 'point'
                    ? 'cursor-crosshair'
                    : 'pointer-events-none'
                  : viewTool === 'pan'
                    ? 'pointer-events-none'
                    : editMode
                      ? 'cursor-crosshair'
                      : 'cursor-pointer'
              }`}
              viewBox="0 0 1 1"
              preserveAspectRatio="none"
              onPointerDown={(e) => {
                if (overlayMode === 'seg' && samTool === 'point') {
                  void runSamPoint(e);
                  return;
                }
                onOverlayPointerDown(e, null, 'draw');
              }}
              onPointerMove={onOverlayPointerMove}
              onPointerUp={(e) => void onOverlayPointerUp(e)}
              onPointerCancel={(e) => void onOverlayPointerUp(e)}
            >
              <defs>
                <marker
                  id={`mv-arrow-${viewerId}`}
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="4"
                  markerHeight="4"
                  orient="auto-start-reverse"
                >
                  <path d="M 0 0 L 10 5 L 0 10 z" fill={ACCENT} />
                </marker>
              </defs>
              {overlayMode === 'seg'
                ? segMasks.map((mask, idx) => {
                    const pts = mask.polygon_norm
                      .filter((p) => Array.isArray(p) && p.length >= 2)
                      .map(([x, y]) => `${x},${y}`)
                      .join(' ');
                    if (!pts) return null;
                    const labelX = mask.polygon_norm[0]?.[0] ?? 0.02;
                    const labelY = mask.polygon_norm[0]?.[1] ?? 0.02;
                    return (
                      <g key={`seg-${idx}`}>
                        <polygon
                          points={pts}
                          fill="rgba(232,125,13,0.28)"
                          stroke={ACCENT}
                          strokeWidth={1.25}
                          vectorEffect="non-scaling-stroke"
                        />
                        <text
                          x={Math.min(0.92, Math.max(0.01, labelX + 0.006))}
                          y={Math.min(0.98, Math.max(0.018, labelY - 0.008))}
                          fill={ACCENT}
                          fontSize={0.012}
                          fontFamily="ui-sans-serif, system-ui, sans-serif"
                          style={{ pointerEvents: 'none' }}
                        >
                          {mask.class} {(mask.conf * 100).toFixed(0)}%
                        </text>
                      </g>
                    );
                  })
                : (
                  <>
                    {overlayObjects.map((obj) => {
                const { x1, y1, x2, y2 } = obj.bbox;
                const selected = obj.id === activeDetectionId;
                const color = obj.color || ACCENT;
                const cx = (x1 + x2) / 2;
                const cy = (y1 + y2) / 2;
                const mv = obj.motion;
                const showArrow =
                  showMotion &&
                  mv &&
                  typeof mv.vx === 'number' &&
                  typeof mv.vy === 'number' &&
                  (Math.abs(mv.vx) > 0.0005 || Math.abs(mv.vy) > 0.0005);
                // Scale vectors for visibility (normalized coords)
                const scale = 6;
                const ax2 = showArrow ? Math.min(1, Math.max(0, cx + mv!.vx * scale)) : cx;
                const ay2 = showArrow ? Math.min(1, Math.max(0, cy + mv!.vy * scale)) : cy;
                return (
                  <g key={obj.id}>
                    <rect
                      x={x1}
                      y={y1}
                      width={x2 - x1}
                      height={y2 - y1}
                      fill={selected ? 'rgba(232,125,13,0.15)' : 'rgba(0,0,0,0)'}
                      stroke={color}
                      strokeWidth={selected ? 2 : 1.5}
                      vectorEffect="non-scaling-stroke"
                      className={editMode ? 'cursor-move' : undefined}
                      onPointerDown={(e) => onOverlayPointerDown(e, obj.id, 'move')}
                    />
                    {showArrow && (
                      <line
                        x1={cx}
                        y1={cy}
                        x2={ax2}
                        y2={ay2}
                        stroke={ACCENT}
                        strokeWidth={1.5}
                        vectorEffect="non-scaling-stroke"
                        markerEnd={`url(#mv-arrow-${viewerId})`}
                        style={{ pointerEvents: 'none' }}
                      />
                    )}
                    <text
                      x={x1 + 0.006}
                      y={Math.max(0.018, y1 - 0.012)}
                      fill={color}
                      fontSize={0.012}
                      fontFamily="ui-sans-serif, system-ui, sans-serif"
                      style={{ pointerEvents: 'none' }}
                    >
                      {obj.track_id != null ? `#${obj.track_id} ` : ''}
                      {obj.class_ru || obj.class_en} {(obj.confidence * 100).toFixed(0)}%
                    </text>
                    {editMode &&
                      selected &&
                      HANDLES.map((h) => {
                        const pos = handlePos(obj.bbox, h);
                        return (
                          <rect
                            key={h}
                            x={pos.x - 0.01}
                            y={pos.y - 0.01}
                            width={0.02}
                            height={0.02}
                            fill="#fff"
                            stroke={ACCENT}
                            strokeWidth={1.5}
                            vectorEffect="non-scaling-stroke"
                            className="cursor-pointer"
                            onPointerDown={(e) => onOverlayPointerDown(e, obj.id, h)}
                          />
                        );
                      })}
                  </g>
                );
              })}
                    {segMasks.map((mask, idx) => {
                      const pts = mask.polygon_norm
                        .filter((p) => Array.isArray(p) && p.length >= 2)
                        .map(([x, y]) => `${x},${y}`)
                        .join(' ');
                      if (!pts) return null;
                      const labelX = mask.polygon_norm[0]?.[0] ?? 0.02;
                      const labelY = mask.polygon_norm[0]?.[1] ?? 0.02;
                      return (
                        <g key={`sam-freeze-${idx}`} style={{ pointerEvents: 'none' }}>
                          <polygon
                            points={pts}
                            fill="rgba(232,125,13,0.28)"
                            stroke={ACCENT}
                            strokeWidth={1.25}
                            vectorEffect="non-scaling-stroke"
                          />
                          <text
                            x={Math.min(0.92, Math.max(0.01, labelX + 0.006))}
                            y={Math.min(0.98, Math.max(0.018, labelY - 0.008))}
                            fill={ACCENT}
                            fontSize={0.012}
                            fontFamily="ui-sans-serif, system-ui, sans-serif"
                          >
                            {mask.class} {(mask.conf * 100).toFixed(0)}%
                          </text>
                        </g>
                      );
                    })}
                  </>
                )}
              {compareMode &&
                changeOverlays.map((co) => {
                  const { x1, y1, x2, y2 } = co.bbox;
                  const color = CHANGE_COLORS[co.changeType];
                  return (
                    <g key={`chg-${co.id}-${co.changeType}`} style={{ pointerEvents: 'none' }}>
                      <rect
                        x={x1}
                        y={y1}
                        width={x2 - x1}
                        height={y2 - y1}
                        fill={
                          co.highlighted
                            ? `${color}33`
                            : co.changeType === 'moved'
                              ? 'rgba(234,179,8,0.12)'
                              : 'rgba(0,0,0,0)'
                        }
                        stroke={color}
                        strokeWidth={co.highlighted ? 3 : 2}
                        vectorEffect="non-scaling-stroke"
                      />
                      <text
                        x={x1 + 0.006}
                        y={Math.max(0.018, y1 - 0.012)}
                        fill={color}
                        fontSize={0.012}
                        fontFamily="ui-sans-serif, system-ui, sans-serif"
                      >
                        {co.class_name}
                      </text>
                    </g>
                  );
                })}
              {overlayMode !== 'seg' && draft && (
                <rect
                  x={draft.x1}
                  y={draft.y1}
                  width={Math.max(0, draft.x2 - draft.x1)}
                  height={Math.max(0, draft.y2 - draft.y1)}
                  fill="rgba(232,125,13,0.12)"
                  stroke={ACCENT}
                  strokeDasharray="6 4"
                  strokeWidth={1.5}
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
          </div>
            {scrubDuration > 0 && (
              <div
                data-testid="viewer-scrub"
                className="absolute left-0 right-0 bottom-0 h-6 bg-black/80 z-20 cursor-ew-resize select-none"
                onPointerDown={(e) => {
                  e.stopPropagation();
                  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
                  setScrubDragging(true);
                  startScrubbing(scrubTimeFromClientX(e.clientX, e.currentTarget));
                }}
                onPointerMove={(e) => {
                  if (!scrubDragging) return;
                  updateScrubPosition(scrubTimeFromClientX(e.clientX, e.currentTarget));
                }}
                onPointerUp={() => {
                  setScrubDragging(false);
                  endScrubbing();
                }}
                onPointerCancel={() => {
                  setScrubDragging(false);
                  endScrubbing();
                }}
              >
                <span className="absolute left-1 top-0.5 text-[9px] font-mono text-gray-200 pointer-events-none z-10">
                  {formatMediaTime(displayScrubTime)} / {formatMediaTime(scrubDuration)}
                </span>
                {inPoint != null && outPoint != null && outPoint > inPoint && (
                  <div
                    className="absolute top-0 bottom-0 bg-blue-400/35 border-l border-r border-blue-300"
                    style={{
                      left: `${(inPoint / scrubDuration) * 100}%`,
                      width: `${((outPoint - inPoint) / scrubDuration) * 100}%`,
                    }}
                  />
                )}
                {inPoint != null && (
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-blue-400"
                    style={{ left: `${(inPoint / scrubDuration) * 100}%` }}
                  >
                    <span className="absolute -top-0.5 left-1 text-[8px] text-blue-200 font-mono">I</span>
                  </div>
                )}
                {outPoint != null && (
                  <div
                    className="absolute top-0 bottom-0 w-0.5 bg-red-400"
                    style={{ left: `${(outPoint / scrubDuration) * 100}%` }}
                  >
                    <span className="absolute -top-0.5 left-1 text-[8px] text-red-200 font-mono">O</span>
                  </div>
                )}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-[var(--dv-accent)]"
                  style={{ left: `${(displayScrubTime / scrubDuration) * 100}%` }}
                />
              </div>
            )}
          </>
        ) : (
          <div className="text-xs text-[var(--dv-text-muted)] text-center px-4">
            <div className="mb-2 opacity-60">No media loaded</div>
            <div>
              Engine: YOLO26 · {inferKind} · {inferN} obj · {inferMs}ms ({status})
            </div>
          </div>
        )}
      </div>
      {viewerId === 'viewer-1' && compareMode && syncModalOpen ? (
        <CompareSyncModal
          isOpen={syncModalOpen}
          onClose={() => setSyncModalOpen(false)}
          videoBefore={useViewerStore.getState().viewers['viewer-1']?.sourcePath || ''}
          videoAfter={useViewerStore.getState().viewers['viewer-2']?.sourcePath || ''}
          onSyncComplete={({ timeBefore, timeAfter }) => {
            cdRequestSeek(timeBefore, timeAfter);
          }}
        />
      ) : null}
      {overlayMode === 'seg' && batchSegOpen ? (
        <BatchSegModal
          open={batchSegOpen}
          videoPath={viewer?.sourcePath || ''}
          onClose={() => setBatchSegOpen(false)}
          onPickFrame={(timeSec, masks) => {
            setPaused(true);
            seekTo(timeSec);
            applyVideoSeek(timeSec, { force: true });
            const mapped: SegMask[] = (masks as BatchSegMask[]).map((m) => ({
              class: m.class,
              conf: m.conf,
              polygon_norm: m.polygon_norm,
            }));
            setSegMasks(mapped);
            setOverlayMode('seg');
          }}
        />
      ) : null}
      {overlayMode === 'seg' && samPropOpen ? (
        <Sam3PropagateModal
          open={samPropOpen}
          videoPath={viewer?.sourcePath || ''}
          timeSec={overlayTimeSec}
          onClose={() => setSamPropOpen(false)}
          onPickFrame={(timeSec, masks) => {
            setPaused(true);
            seekTo(timeSec);
            applyVideoSeek(timeSec, { force: true });
            setSegMasks(
              masks.map((m) => ({
                class: m.class,
                conf: m.conf,
                polygon_norm: m.polygon_norm,
              })),
            );
            setOverlayMode('seg');
          }}
        />
      ) : null}
    </div>
  );
};

export default Viewer;
