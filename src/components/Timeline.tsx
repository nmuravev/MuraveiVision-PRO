import React, { memo, useEffect, useMemo, useRef, useState } from 'react';
import { Play, Pause, SkipBack, SkipForward, ZoomIn, ZoomOut, X } from 'lucide-react';
import { classLabelRu } from '../lib/classLabels';
import { useTimelineStore, ZOOM_PRESETS } from '../store/timeline-store';

function useTimelineScrub() {
  const startScrubbing = useTimelineStore((s) => s.startScrubbing);
  const updateScrubPosition = useTimelineStore((s) => s.updateScrubPosition);
  const endScrubbing = useTimelineStore((s) => s.endScrubbing);
  return { startScrubbing, updateScrubPosition, endScrubbing };
}

const FILMSTRIP_DRAG_PX = 5;

export interface DetectionMarker {
  id: string;
  timestamp: number;
  class_ru: string;
  class_en: string;
  confidence: number;
  color: string;
  gpsLabel?: string;
}

interface TimelineProps {
  duration: number;
  currentTime: number;
  detections: DetectionMarker[];
  onSeek: (time: number) => void;
  onPlayPause: () => void;
  isPlaying: boolean;
  inPoint?: number | null;
  outPoint?: number | null;
  onSetInPoint?: () => void;
  onSetOutPoint?: () => void;
  onClearInOut?: () => void;
  onZoomIn?: () => void;
  onZoomOut?: () => void;
  previewFrame?: string | null;
  filmstrip?: { t: number; image: string }[];
  onDeleteDetection?: (id: string) => void;
  onSelectDetection?: (id: string) => void;
}

const CLASS_COLORS: Record<string, string> = {
  tank: '#ef4444',
  armored_vehicle: '#f97316',
  uav: '#eab308',
  quadcopter_drone: '#eab308',
  fpv_drone: '#eab308',
  soldier: '#22c55e',
  artillery: '#a855f7',
  mine: '#f43f5e',
  anti_tank_mine: '#f43f5e',
  anti_personnel_mine: '#f43f5e',
  default: '#64748b',
};

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

function tickStep(pps: number, duration: number): number {
  const safePps = Number.isFinite(pps) && pps > 0 ? pps : 10;
  const safeDur = Number.isFinite(duration) && duration > 0 ? duration : 120;
  if (safePps >= 80) return 1;
  if (safePps >= 40) return 2;
  if (safePps >= 20) return 5;
  if (safeDur > 180) return 30;
  return 10;
}

const TimelineMarker = memo(function TimelineMarker({
  det,
  safeDur,
  onSeek,
  onSelectDetection,
  onDeleteDetection,
}: {
  det: DetectionMarker;
  safeDur: number;
  onSeek: (t: number) => void;
  onSelectDetection?: (id: string) => void;
  onDeleteDetection?: (id: string) => void;
}) {
  const pct = Math.max(0, Math.min(100, (det.timestamp / safeDur) * 100));
  return (
    <div
      className="absolute top-1/2 w-1.5 h-7 -ml-[3px] rounded-sm cursor-pointer hover:scale-125 transition-transform group z-[5]"
      style={{
        left: `${pct}%`,
        transform: 'translate3d(0, -50%, 0)',
        backgroundColor: CLASS_COLORS[det.class_en] || CLASS_COLORS.default,
        willChange: 'transform',
      }}
      title={`${det.class_ru} @ ${formatTime(det.timestamp)}${det.gpsLabel ? ` · ${det.gpsLabel}` : ''} — ПКМ удалить`}
      onPointerDown={(e) => {
        e.stopPropagation();
        if (e.altKey) {
          onDeleteDetection?.(det.id);
          return;
        }
        onSelectDetection?.(det.id);
        onSeek(det.timestamp);
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onDeleteDetection?.(det.id);
      }}
    />
  );
});

export const Timeline: React.FC<TimelineProps> = ({
  duration,
  currentTime,
  detections,
  onSeek,
  onPlayPause,
  isPlaying,
  inPoint,
  outPoint,
  onSetInPoint,
  onSetOutPoint,
  onClearInOut,
  onZoomIn,
  onZoomOut,
  previewFrame,
  filmstrip = [],
  onDeleteDetection,
  onSelectDetection,
}) => {
  const timelineRef = useRef<HTMLDivElement>(null);
  const filmstripRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const filmDragRef = useRef<{ startX: number; dragged: boolean } | null>(null);
  const pixelsPerSecond = useTimelineStore((s) => s.pixelsPerSecond);
  const viewportWidth = useTimelineStore((s) => s.viewportWidth);
  const scrollX = useTimelineStore((s) => s.scrollX);
  const setViewportDimensions = useTimelineStore((s) => s.setViewportDimensions);
  const setScrollX = useTimelineStore((s) => s.setScrollX);
  const playbackRate = useTimelineStore((s) => s.playbackRate);
  const setPlaybackRate = useTimelineStore((s) => s.setPlaybackRate);
  const { startScrubbing, updateScrubPosition, endScrubbing } = useTimelineScrub();
  const finiteDur = Number.isFinite(duration) && duration > 0 ? duration : 120;
  const safeDur = Math.max(0.001, finiteDur);
  const safePps = Number.isFinite(pixelsPerSecond) && pixelsPerSecond > 0 ? pixelsPerSecond : 10;
  const innerWidth = Math.max(viewportWidth || 1, finiteDur * safePps);
  const fittedKeyRef = useRef('');
  const filmstripPath = useTimelineStore((s) => s.filmstripPath);

  useEffect(
    () => () => {
      if (filmDragRef.current) {
        filmDragRef.current = null;
        endScrubbing();
      }
    },
    [endScrubbing],
  );

  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => {
      setViewportDimensions(el.clientWidth, el.clientHeight);
    });
    ro.observe(el);
    setViewportDimensions(el.clientWidth, el.clientHeight);
    return () => ro.disconnect();
  }, [setViewportDimensions]);

  useEffect(() => {
    if (!Number.isFinite(duration) || duration <= 1) return;
    const key = `${filmstripPath ?? ''}|${Math.round(duration)}`;
    if (fittedKeyRef.current === key) return;
    fittedKeyRef.current = key;
    useTimelineStore.getState().zoomToFit(duration);
  }, [duration, filmstripPath]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (Math.abs(el.scrollLeft - scrollX) > 2) {
      el.scrollLeft = scrollX;
    }
  }, [scrollX, pixelsPerSecond, innerWidth]);

  const timeFromEvent = (clientX: number) => {
    if (!timelineRef.current) return 0;
    const rect = timelineRef.current.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(1, rect.width)));
    return percent * finiteDur;
  };

  const timeFromFilmstrip = (clientX: number) => {
    const el = filmstripRef.current;
    if (!el) return 0;
    const rect = el.getBoundingClientRect();
    const percent = Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(1, rect.width)));
    return percent * finiteDur;
  };

  const onPointerDown = (e: React.PointerEvent) => {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDragging(true);
    startScrubbing(timeFromEvent(e.clientX));
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging) return;
    updateScrubPosition(timeFromEvent(e.clientX));
  };

  const onPointerUp = (e: React.PointerEvent) => {
    setDragging(false);
    endScrubbing();
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const onFilmstripPointerDown = (e: React.PointerEvent, frameT: number) => {
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    filmDragRef.current = { startX: e.clientX, dragged: false };
    startScrubbing(frameT);
  };

  const onFilmstripPointerMove = (e: React.PointerEvent) => {
    const drag = filmDragRef.current;
    if (!drag) return;
    if (!drag.dragged && Math.abs(e.clientX - drag.startX) >= FILMSTRIP_DRAG_PX) {
      drag.dragged = true;
    }
    if (drag.dragged) {
      updateScrubPosition(timeFromFilmstrip(e.clientX));
    }
  };

  const onFilmstripPointerUp = (e: React.PointerEvent) => {
    // Always end scrub so YOLO suspend arms/clears via Viewer; click = seek via endScrubbing→seekTo
    endScrubbing();
    filmDragRef.current = null;
    try {
      (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {
      /* ignore */
    }
  };

  const playheadPct = Math.max(0, Math.min(100, (currentTime / safeDur) * 100));
  const hasRange = inPoint != null && outPoint != null && outPoint > inPoint;
  const step = tickStep(safePps, finiteDur);
  const tickCount = Math.min(500, Math.max(1, Math.ceil(finiteDur / step) + 1));
  const tickIndices = useMemo(() => {
    const list: number[] = [];
    for (let i = 0; i < tickCount; i++) {
      list.push(i);
    }
    return list;
  }, [tickCount]);
  const [timelineNarrow, setTimelineNarrow] = useState(false);
  const chromeRef = useRef<HTMLDivElement>(null);
  const storeZoomIn = useTimelineStore((s) => s.zoomIn);
  const storeZoomOut = useTimelineStore((s) => s.zoomOut);
  const doZoomIn = onZoomIn ?? storeZoomIn;
  const doZoomOut = onZoomOut ?? storeZoomOut;
  const atMaxZoom = pixelsPerSecond >= ZOOM_PRESETS.MAX - 0.01;
  const atMinZoom = pixelsPerSecond <= ZOOM_PRESETS.MIN + 0.01;

  useEffect(() => {
    const el = chromeRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      setTimelineNarrow(w < 720);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className="h-full flex flex-col bg-[#1a1a1a] border-t border-gray-800">
      <div
        ref={chromeRef}
        className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 min-w-0 w-full"
      >
        <div className="flex items-center gap-2 shrink-0">
          <button type="button" onClick={onPlayPause} className="p-1.5 hover:bg-gray-700 rounded text-gray-300" title="Play/Pause (Space)">
            {isPlaying ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <button type="button" onClick={() => onSeek(0)} className="p-1.5 hover:bg-gray-700 rounded text-gray-300" title="В начало">
            <SkipBack size={16} />
          </button>
          <button
            type="button"
            onClick={() => onSeek(duration)}
            className="p-1.5 hover:bg-gray-700 rounded text-gray-300"
            title="В конец"
          >
            <SkipForward size={16} />
          </button>

          <div className="w-px h-4 bg-gray-700 mx-1" />

          <span className="text-xs font-mono text-gray-300 min-w-[72px]">
            {formatTime(currentTime)} / {formatTime(duration)}
          </span>
          <select
            aria-label="Скорость воспроизведения"
            className="bg-[#111] border border-gray-700 px-1 py-0.5 text-[10px] font-mono text-gray-300"
            value={playbackRate}
            onChange={(event) => setPlaybackRate(Number(event.target.value))}
          >
            {[0.25, 0.5, 1, 1.5, 2, 4].map((rate) => (
              <option key={rate} value={rate}>
                {rate}×
              </option>
            ))}
          </select>

          <div className="w-px h-4 bg-gray-700 mx-1" />

          <button
            type="button"
            onClick={onSetInPoint}
            className="px-1.5 py-0.5 hover:bg-blue-800 rounded text-blue-400 font-mono text-xs font-bold"
            title="Метка In — начало участка анализа (клавиша I)"
          >
            I
          </button>
          <button
            type="button"
            onClick={onSetOutPoint}
            className="px-1.5 py-0.5 hover:bg-red-800 rounded text-red-400 font-mono text-xs font-bold"
            title="Метка Out — конец участка анализа (клавиша O)"
          >
            O
          </button>
          {(inPoint != null || outPoint != null) && (
            <button
              type="button"
              onClick={onClearInOut}
              className="p-1 hover:bg-gray-700 rounded text-gray-400"
              title="Сбросить In/Out"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <div className="min-w-0 flex-1 overflow-x-auto flex items-center gap-2">
          {!timelineNarrow && (
            <>
              <span className="text-[10px] font-mono text-blue-300 min-w-[88px] shrink-0">
                I {inPoint != null ? formatTime(inPoint) : '--:--'}
              </span>
              <span className="text-[10px] font-mono text-red-300 min-w-[88px] shrink-0">
                O {outPoint != null ? formatTime(outPoint) : '--:--'}
              </span>
            </>
          )}
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {!timelineNarrow && (
            <span className="text-[10px] font-mono text-gray-500 min-w-[52px] text-right">
              {pixelsPerSecond.toFixed(0)} px/s
            </span>
          )}
          <button
            type="button"
            onClick={() => doZoomOut()}
            disabled={atMinZoom}
            className="p-1.5 hover:bg-gray-700 rounded text-gray-300 disabled:opacity-40"
            title="Zoom out"
          >
            <ZoomOut size={16} />
          </button>
          <button
            type="button"
            onClick={() => doZoomIn()}
            disabled={atMaxZoom}
            className="p-1.5 hover:bg-gray-700 rounded text-gray-300 disabled:opacity-40"
            title="Zoom in"
          >
            <ZoomIn size={16} />
          </button>
        </div>
      </div>

      <div className="flex-1 relative min-h-0">
        <div
          ref={scrollRef}
          className="absolute inset-0 overflow-x-auto overflow-y-hidden"
          onScroll={(e) => setScrollX(e.currentTarget.scrollLeft)}
        >
          <div className="relative h-full" style={{ width: innerWidth, minWidth: '100%' }}>
            <div className="absolute top-0 left-0 right-0 h-14 bg-black overflow-hidden border-b border-gray-800">
              <div ref={filmstripRef} className="absolute inset-0">
                {filmstrip.length > 0 ? (
                  filmstrip.map((frame, i) => {
                    const nextT = i < filmstrip.length - 1 ? filmstrip[i + 1].t : duration;
                    const span = Math.max(0.01, nextT - frame.t);
                    const left = Math.max(0, Math.min(100, (frame.t / safeDur) * 100));
                    const width = Math.max(0.01, Math.min(100 - left, (span / safeDur) * 100));
                    return (
                      <button
                        key={`${frame.t}-${i}`}
                        type="button"
                        className="absolute top-0 bottom-0 p-0 border-0 overflow-hidden cursor-ew-resize"
                        style={{
                          left: `${left}%`,
                          width: `${width}%`,
                        }}
                        title={formatTime(frame.t)}
                        onPointerDown={(e) => onFilmstripPointerDown(e, frame.t)}
                        onPointerMove={onFilmstripPointerMove}
                        onPointerUp={onFilmstripPointerUp}
                        onPointerCancel={onFilmstripPointerUp}
                        onLostPointerCapture={() => {
                          if (!filmDragRef.current) return;
                          filmDragRef.current = null;
                          endScrubbing();
                        }}
                      >
                        <img src={frame.image} alt="" className="h-full w-full object-cover pointer-events-none" draggable={false} />
                      </button>
                    );
                  })
                ) : previewFrame ? (
                  <img src={previewFrame} alt="frame" className="h-full object-contain" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-600">
                    Filmstrip появится после загрузки видео
                  </div>
                )}
              </div>
              {hasRange && inPoint != null && outPoint != null && (
                <div
                  className="absolute top-0 bottom-0 bg-blue-400/25 border-l-2 border-r-2 border-blue-400 pointer-events-none z-10"
                  style={{
                    left: `${(inPoint / safeDur) * 100}%`,
                    width: `${((outPoint - inPoint) / safeDur) * 100}%`,
                  }}
                />
              )}
            </div>

            <div
              ref={timelineRef}
              data-testid="timeline-scrub"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              className="absolute left-0 right-0 bottom-6 top-14 cursor-ew-resize bg-[#0f0f0f]"
            >
              {hasRange && inPoint != null && outPoint != null && (
                <div
                  className="absolute top-0 bottom-0 bg-blue-500/20 border-l-2 border-r-2 border-blue-400 pointer-events-none"
                  style={{
                    left: `${(inPoint / safeDur) * 100}%`,
                    width: `${((outPoint - inPoint) / safeDur) * 100}%`,
                  }}
                />
              )}
              {inPoint != null && (
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-blue-400 pointer-events-none"
                  style={{ left: `${(inPoint / safeDur) * 100}%` }}
                >
                  <span className="absolute top-0 left-1 text-[9px] text-blue-300 font-mono">I</span>
                </div>
              )}
              {outPoint != null && (
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-red-400 pointer-events-none"
                  style={{ left: `${(outPoint / safeDur) * 100}%` }}
                >
                  <span className="absolute top-0 left-1 text-[9px] text-red-300 font-mono">O</span>
                </div>
              )}

              {detections.map((det) => (
                <TimelineMarker
                  key={det.id}
                  det={det}
                  safeDur={safeDur}
                  onSeek={onSeek}
                  onSelectDetection={onSelectDetection}
                  onDeleteDetection={onDeleteDetection}
                />
              ))}

              <div
                className="absolute top-0 bottom-0 w-0.5 bg-red-500 pointer-events-none z-10"
                style={{ left: `${playheadPct}%` }}
              >
                <div className="absolute -top-1 -left-1.5 w-3 h-3 bg-red-500 rounded-full" />
              </div>
            </div>

            <div className="absolute bottom-0 left-0 right-0 h-6 bg-[#0a0a0a] border-t border-gray-800">
              {tickIndices.map((i: number) => (
                <div
                  key={i}
                  className="absolute text-[10px] font-mono text-gray-500"
                  style={{ left: `${Math.max(0, Math.min(100, ((i * step) / safeDur) * 100))}%` }}
                >
                  {formatTime(i * step)}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-3 px-3 py-1.5 border-t border-gray-800 text-[10px] min-h-[28px]">
        {Object.entries(CLASS_COLORS)
          .filter(([k]) => k !== 'default')
          .map(([cls, color]) => (
            <div key={cls} className="flex items-center gap-1 shrink-0">
              <div className="w-2 h-2 rounded" style={{ backgroundColor: color }} />
              <span className="text-gray-400">{classLabelRu(undefined, cls, [])}</span>
            </div>
          ))}
      </div>
    </div>
  );
};

export default Timeline;
