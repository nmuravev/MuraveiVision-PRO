// KEEP: session trace — do not remove without explicit user order
import React, { useEffect, useMemo, useState } from 'react';
import { ImageOff, Trash2 } from 'lucide-react';
import {
  archiveMediaPath,
  detectionCropSrc,
  toDetectedObject,
  useMuraveiStore,
} from '../../store/useMuraveiStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { mediaPathsMatch } from '../../lib/mediaPaths';
import {
  buildDetectionTracks,
  formatTrackRange,
  type DetectionTrack,
} from '../../lib/detectionTracks';
import { logger } from '../../services/logger';

const VISIBLE_CAP = 96;

const CropThumb: React.FC<{ id: string; cropPath?: string | null; alt: string }> = ({
  id,
  cropPath,
  alt,
}) => {
  const [failed, setFailed] = useState(false);
  const src = detectionCropSrc(id, cropPath);

  if (failed || !id) {
    return (
      <div className="w-full h-16 mb-1 rounded-sm bg-[#1a1a1a] border border-[var(--dv-border)] flex flex-col items-center justify-center gap-0.5 text-[var(--dv-text-muted)]">
        <ImageOff size={14} />
        <span className="text-[9px]">нет изображения</span>
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      className="w-full h-16 mb-1 object-cover rounded-sm bg-black pointer-events-none"
      onError={() => {
        setFailed(true);
        logger.warn('gallery', `Кроп не загружен: ${cropPath || id}`);
      }}
    />
  );
};

export const BattleGallery: React.FC = () => {
  const detections = useMuraveiStore((s) => s.detections);
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const clearDetections = useMuraveiStore((s) => s.clearDetections);
  const deleteAllForSource = useMuraveiStore((s) => s.deleteAllForSource);
  const setActiveDetection = useMuraveiStore((s) => s.setActiveDetection);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const deleteDetection = useMuraveiStore((s) => s.deleteDetection);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const markIn = useTimelineStore((s) => s.markIn);
  const markOut = useTimelineStore((s) => s.markOut);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const setSource = useViewerStore((s) => s.setSource);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);
  const [clearBusy, setClearBusy] = useState(false);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (!sourcePath) {
      clearDetections();
      return;
    }
    void hydrateDetections(sourcePath);
  }, [isAuthenticated, sourcePath, hydrateDetections, clearDetections]);

  const scoped = useMemo(() => {
    const rows = sourcePath
      ? detections.filter((d) => mediaPathsMatch(d.source_video || '', sourcePath))
      : [];
    return rows;
  }, [detections, sourcePath]);

  const tracks = useMemo(() => buildDetectionTracks(scoped), [scoped]);
  const visible = tracks.slice(0, VISIBLE_CAP);

  const openTrack = (t: DetectionTrack) => {
    const row = t.primary;
    setActiveDetection(toDetectedObject(row));
    if (row.source_video) {
      setSource(focusedViewerId || 'viewer-1', archiveMediaPath(row.source_video), null);
    }
    seekTo(t.tIn);
    markIn(t.tIn);
    markOut(Math.max(t.tOut, t.tIn + 0.05));
  };

  return (
    <div className="h-full overflow-auto p-2">
      <div className="mb-2 flex items-center justify-between gap-2 text-[10px] text-[var(--dv-text-muted)]">
        <span>
          Треки · {tracks.length}
          {scoped.length !== tracks.length ? ` · кадров ${scoped.length}` : ''}
          {tracks.length > VISIBLE_CAP ? ` · показ ${VISIBLE_CAP}` : ''}
        </span>
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm text-[10px] text-red-400 border border-[var(--dv-border)] disabled:opacity-40"
          disabled={!sourcePath || scoped.length === 0 || clearBusy}
          title="Удалить все детекции текущего ролика"
          onClick={() => {
            if (!sourcePath) return;
            if (!window.confirm(`Очистить ${scoped.length} кадров (${tracks.length} треков) этого ролика?`))
              return;
            setClearBusy(true);
            void deleteAllForSource(sourcePath).finally(() => setClearBusy(false));
          }}
        >
          {clearBusy ? '…' : 'Очистить ролик'}
        </button>
      </div>
      {scoped.length === 0 ? (
        <div className="text-xs text-[var(--dv-text-muted)]">
          Треки появятся после «Сканировать» или «Зафиксировать кадр»
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {visible.map((t) => {
            const row = t.primary;
            const selected = t.members.some((m) => m.id === activeDetectionId);
            return (
              <div
                key={t.trackId}
                role="button"
                tabIndex={0}
                className={`group relative aspect-video bg-[var(--dv-bg-deep)] text-left p-1.5 rounded-sm transition-transform duration-150 hover:scale-105 hover:z-10 cursor-pointer ${
                  selected
                    ? 'border-2 border-[var(--dv-accent)] ring-1 ring-[var(--dv-accent)]/40'
                    : 'border border-[var(--dv-border)] hover:border-[var(--dv-accent)]'
                }`}
                onClick={() => openTrack(t)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    openTrack(t);
                  }
                }}
              >
                <CropThumb id={row.id} cropPath={row.crop_path} alt={row.class_name} />
                <div className="text-[10px] truncate text-[var(--dv-text)]">{t.class_name}</div>
                <div className="text-[9px] text-[var(--dv-text-muted)] font-mono truncate">
                  {formatTrackRange(t.tIn, t.tOut)}
                  {t.duration_sec >= 1 ? ` · ${Math.round(t.duration_sec)}с` : ''}
                  {t.count > 1 ? ` · ${t.count}к` : ''}
                </div>
                <button
                  type="button"
                  className="absolute top-1 right-1 p-0.5 rounded bg-black/60 text-red-400 opacity-0 group-hover:opacity-100"
                  title="Удалить кадр-представитель (не весь трек)"
                  onClick={(e) => {
                    e.stopPropagation();
                    void deleteDetection(row.id);
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default BattleGallery;
