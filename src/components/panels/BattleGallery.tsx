import React, { useEffect, useMemo, useState } from 'react';
import { ImageOff, Trash2 } from 'lucide-react';
import {
  detectionCropSrc,
  toDetectedObject,
  useMuraveiStore,
} from '../../store/useMuraveiStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { mediaPathsMatch } from '../../lib/mediaPaths';
import { logger } from '../../services/logger';

function formatTs(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const CropThumb: React.FC<{ id: string; cropPath?: string | null; alt: string }> = ({
  id,
  cropPath,
  alt,
}) => {
  const [failed, setFailed] = useState(false);
  const src = detectionCropSrc(id, cropPath);

  if (failed || (!cropPath && !id)) {
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
  const setActiveDetection = useMuraveiStore((s) => s.setActiveDetection);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const deleteDetection = useMuraveiStore((s) => s.deleteDetection);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const setSource = useViewerStore((s) => s.setSource);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);

  useEffect(() => {
    if (!isAuthenticated) return;
    if (!sourcePath) {
      clearDetections();
      return;
    }
    void hydrateDetections(sourcePath);
  }, [isAuthenticated, sourcePath, hydrateDetections, clearDetections]);

  const items = useMemo(() => {
    const scoped = sourcePath
      ? detections.filter((d) => mediaPathsMatch(d.source_video || '', sourcePath))
      : [];
    return [...scoped].reverse();
  }, [detections, sourcePath]);

  return (
    <div className="h-full overflow-auto p-2">
      <div className="mb-2 text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
        Кропы · {items.length}
      </div>
      {items.length === 0 ? (
        <div className="text-xs text-[var(--dv-text-muted)]">
          Кропы появляются после «Зафиксировать кадр»
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {items.map((row) => {
            const selected = row.id === activeDetectionId;
            return (
              <div
                key={row.id}
                role="button"
                tabIndex={0}
                className={`group relative aspect-video bg-[var(--dv-bg-deep)] text-left p-1.5 rounded-sm transition-transform duration-150 hover:scale-105 hover:z-10 cursor-pointer ${
                  selected
                    ? 'border-2 border-[var(--dv-accent)] ring-1 ring-[var(--dv-accent)]/40'
                    : 'border border-[var(--dv-border)] hover:border-[var(--dv-accent)]'
                }`}
                onClick={() => {
                  setActiveDetection(toDetectedObject(row));
                  if (row.source_video) {
                    setSource(focusedViewerId || 'viewer-1', row.source_video, null);
                  }
                  seekTo(row.time_sec);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActiveDetection(toDetectedObject(row));
                    seekTo(row.time_sec);
                  }
                }}
              >
                <CropThumb id={row.id} cropPath={row.crop_path} alt={row.class_name} />
                <div className="text-[10px] truncate text-[var(--dv-text)]">{row.class_name}</div>
                <div className="text-[9px] text-[var(--dv-text-muted)] font-mono">
                  {formatTs(row.time_sec)}
                </div>
                <button
                  type="button"
                  className="absolute top-1 right-1 p-0.5 rounded bg-black/60 text-red-400 opacity-0 group-hover:opacity-100"
                  title="Удалить"
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
