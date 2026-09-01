import React, { useEffect, useMemo } from 'react';
import { Timeline, type DetectionMarker } from '../Timeline';
import { useMuraveiStore } from '../../store/useMuraveiStore';
import { batchScanProgressPct, useBatchScanStore } from '../../store/useBatchScanStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { classLabelRu } from '../../lib/classLabels';
import { mediaPathsMatch } from '../../lib/mediaPaths';

export const TimelinePanel: React.FC = () => {
  const detections = useMuraveiStore((s) => s.detections);
  const classCatalog = useMuraveiStore((s) => s.classCatalog);
  const deleteDetection = useMuraveiStore((s) => s.deleteDetection);
  const setActiveDetectionId = useMuraveiStore((s) => s.setActiveDetectionId);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const playbackState = useTimelineStore((s) => s.playbackState);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);
  const previewFrame = useTimelineStore((s) => s.previewFrame);
  const filmstrip = useTimelineStore((s) => s.filmstrip);
  const filmstripPath = useTimelineStore((s) => s.filmstripPath);
  const setFilmstrip = useTimelineStore((s) => s.setFilmstrip);
  const inPoint = useTimelineStore((s) => s.inPoint);
  const outPoint = useTimelineStore((s) => s.outPoint);
  const liveMarks = useTimelineStore((s) => s.liveMarks);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const pause = useTimelineStore((s) => s.pause);
  const togglePlayback = useTimelineStore((s) => s.togglePlayback);
  const markIn = useTimelineStore((s) => s.markIn);
  const markOut = useTimelineStore((s) => s.markOut);
  const clearInOut = useTimelineStore((s) => s.clearInOut);
  const zoomIn = useTimelineStore((s) => s.zoomIn);
  const zoomOut = useTimelineStore((s) => s.zoomOut);
  const removeLiveMark = useTimelineStore((s) => s.removeLiveMark);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);

  const scanStatus = useBatchScanStore((s) => s.status);
  const scanMessage = useBatchScanStore((s) => s.message);
  const scanProcessed = useBatchScanStore((s) => s.processed);
  const scanSampleTotal = useBatchScanStore((s) => s.sampleTotal);
  const scanFound = useBatchScanStore((s) => s.found);
  const scanVideoPath = useBatchScanStore((s) => s.videoPath);

  const fileLabel = sourcePath
    ? sourcePath.replace(/^.*[/\\]/, '')
    : 'нет файла';

  const scanPct = batchScanProgressPct({
    status: scanStatus,
    processed: scanProcessed,
    sampleTotal: scanSampleTotal,
  });

  const scanActiveForFile =
    sourcePath != null &&
    scanVideoPath != null &&
    mediaPathsMatch(sourcePath, scanVideoPath) &&
    (scanStatus === 'running' || scanStatus === 'done' || scanStatus === 'error');

  useEffect(() => {
    if (!sourcePath || mediaDuration <= 0) return;
    if (!/\.(mp4|webm|mov|avi|mkv)$/i.test(sourcePath)) return;
    if (filmstripPath === sourcePath && filmstrip.length >= 8) return;
    const token = localStorage.getItem('muravei-token');
    if (!token) return;
    let cancelled = false;
    const params = new URLSearchParams({
      path: sourcePath,
      count: '40',
      token,
    });
    void fetch(`/api/media/filmstrip?${params}`)
      .then((res) => (res.ok ? res.json() : Promise.reject()))
      .then((data: { frames?: { t: number; image: string }[] }) => {
        if (!cancelled && Array.isArray(data.frames) && data.frames.length) {
          setFilmstrip(sourcePath, data.frames);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [sourcePath, mediaDuration, filmstripPath, filmstrip.length, setFilmstrip]);

  // I / O mark hotkeys are handled globally in src/hooks/useHotkeys.ts.

  const markers: DetectionMarker[] = useMemo(() => {
    const persisted = detections
      .filter((d) => {
        if (d.is_deleted) return false;
        if (!sourcePath) return true;
        return mediaPathsMatch(d.source_video || '', sourcePath);
      })
      .map((d) => ({
        id: d.id,
        timestamp: d.time_sec,
        class_ru: classLabelRu(d.class_id, d.class_name, classCatalog),
        class_en: d.class_name,
        confidence: d.confidence,
        color:
          d.origin === 'batch_scan'
            ? '#38bdf8'
            : d.is_edited
              ? '#e87d0d'
              : '#64748b',
        gpsLabel:
          d.gps_lat != null && d.gps_lon != null
            ? `${d.gps_lat.toFixed(5)}, ${d.gps_lon.toFixed(5)}`
            : undefined,
      }));
    const extra = liveMarks.filter(
      (m) =>
        !persisted.some(
          (p) => p.class_en === m.class_en && Math.abs(p.timestamp - m.timestamp) < 0.35,
        ),
    );
    return [
      ...persisted,
      ...extra.map((m) => ({
        id: m.id,
        timestamp: m.timestamp,
        class_ru: m.class_ru,
        class_en: m.class_en,
        confidence: m.confidence,
        color: '',
      })),
    ];
  }, [detections, liveMarks, sourcePath, classCatalog]);

  const duration = mediaDuration > 0 ? mediaDuration : Math.max(120, playheadPosition + 10);

  const activeGps = useMemo(() => {
    if (!activeDetectionId) return null;
    const row = detections.find((d) => d.id === activeDetectionId);
    if (!row || row.gps_lat == null || row.gps_lon == null) return null;
    const alt =
      row.gps_alt != null ? ` · ${row.gps_alt.toFixed(0)}m` : '';
    return `${row.gps_lat.toFixed(5)}, ${row.gps_lon.toFixed(5)}${alt}`;
  }, [activeDetectionId, detections]);

  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="px-2 py-1 text-[10px] text-[var(--dv-text-muted)] border-b border-[var(--dv-border)] flex-shrink-0 truncate">
        Таймлайн: {fileLabel}
        <span className="text-[var(--dv-text-muted)] opacity-70"> · {focusedViewerId.replace('viewer-', 'вьюер ')}</span>
        {scanActiveForFile && scanStatus === 'running' ? (
          <span className="text-[#38bdf8]">
            {' '}
            · YOLO {scanPct}% · {scanFound} целей
            {scanMessage ? ` · ${scanMessage}` : ''}
          </span>
        ) : null}
        {scanActiveForFile && scanStatus === 'done' ? (
          <span className="text-emerald-400"> · анализ завершён · {scanFound} целей</span>
        ) : null}
        {scanActiveForFile && scanStatus === 'error' ? (
          <span className="text-red-400"> · ошибка анализа: {scanMessage}</span>
        ) : null}
        {activeGps ? (
          <span className="text-[#38bdf8] font-mono"> · GPS {activeGps}</span>
        ) : null}
      </div>
      <div className="flex-1 min-h-0">
        <Timeline
          duration={duration}
          currentTime={Math.min(playheadPosition, duration)}
          detections={markers}
          isPlaying={playbackState === 'playing'}
          onSeek={seekTo}
          onPlayPause={togglePlayback}
          inPoint={inPoint}
          outPoint={outPoint}
          onSetInPoint={() => markIn()}
          onSetOutPoint={() => markOut()}
          onClearInOut={clearInOut}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          previewFrame={previewFrame}
          filmstrip={filmstrip}
          onSelectDetection={(id) => {
            const row = detections.find((d) => d.id === id);
            setActiveDetectionId(id);
            if (row) {
              pause();
              seekTo(row.time_sec);
            }
          }}
          onDeleteDetection={(id) => {
            if (id.startsWith('live-')) {
              removeLiveMark(id);
              return;
            }
            void deleteDetection(id);
          }}
        />
      </div>
    </div>
  );
};

export default TimelinePanel;
