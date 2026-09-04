import React, { useEffect, useState } from 'react';
import { Modal, Button } from '../ui';
import {
  useChangeDetectionStore,
  type SyncSegment,
  type SyncSource,
} from '../../store/useChangeDetectionStore';

export type CompareSyncCompletePair = {
  timeBefore: number;
  timeAfter: number;
};

export type CompareSyncModalProps = {
  isOpen: boolean;
  onClose: () => void;
  videoBefore: string;
  videoAfter: string;
  onSyncComplete: (pair: CompareSyncCompletePair) => void;
};

function formatRange(start: number, end: number): string {
  return `${start.toFixed(1)}с–${end.toFixed(1)}с`;
}

export const CompareSyncModal: React.FC<CompareSyncModalProps> = ({
  isOpen,
  onClose,
  videoBefore,
  videoAfter,
  onSyncComplete,
}) => {
  const [source, setSource] = useState<SyncSource>('auto');
  const runSync = useChangeDetectionStore((s) => s.runSync);
  const syncResult = useChangeDetectionStore((s) => s.syncResult);
  const syncLoading = useChangeDetectionStore((s) => s.syncLoading);
  const syncError = useChangeDetectionStore((s) => s.syncError);

  useEffect(() => {
    if (!isOpen) return;
    void runSync({ videoBefore, videoAfter, source: 'auto' });
    setSource('auto');
  }, [isOpen, videoBefore, videoAfter, runSync]);

  const onSourceChange = (next: SyncSource) => {
    setSource(next);
    void runSync({ videoBefore, videoAfter, source: next });
  };

  const onSegmentClick = (seg: SyncSegment) => {
    onSyncComplete({
      timeBefore: seg.start_before,
      timeAfter: seg.start_after,
    });
    onClose();
  };

  return (
    <Modal
      open={isOpen}
      title="Синхронизация времени"
      onClose={onClose}
      wide
      footer={
        <Button size="sm" onClick={onClose}>
          Закрыть
        </Button>
      }
    >
      <div className="space-y-3 text-xs">
        <div>
          <div className="dv-section-label mb-1">Источник</div>
          <select
            className="w-full bg-dv-deep border border-dv-border px-2 py-1.5 text-[11px] outline-none"
            value={source}
            disabled={syncLoading}
            onChange={(e) => onSourceChange(e.target.value as SyncSource)}
          >
            <option value="auto">Auto</option>
            <option value="tracks">GPS Треки</option>
            <option value="detections">Детекции</option>
          </select>
        </div>

        {syncLoading ? (
          <div className="text-dv-muted">Поиск совпадений…</div>
        ) : null}

        {syncError ? <div className="text-dv-danger">{syncError}</div> : null}

        {syncResult?.method_used === 'none' ? (
          <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 px-2 py-1.5 text-[10px]">
            {syncResult.message ||
              'Совпадений не найдено. Используйте ручной выбор кадров.'}
          </div>
        ) : null}

        {syncResult && syncResult.method_used !== 'none' ? (
          <>
            {syncResult.message ? (
              <div className="border border-amber-500/40 bg-amber-500/10 text-amber-200 px-2 py-1.5 text-[10px]">
                {syncResult.message}
              </div>
            ) : null}
            <div className="text-[10px] text-dv-muted font-mono">
              метод: {syncResult.method_used} · пар: {syncResult.pair_count_total} ·
              сегментов: {syncResult.segments.length}
            </div>
            <div>
              <div className="dv-section-label mb-1">Сегменты</div>
              {syncResult.segments.length === 0 ? (
                <div className="text-dv-muted text-[10px]">нет сегментов</div>
              ) : (
                <ul className="max-h-48 overflow-auto space-y-0.5 border border-dv-border bg-dv-deep">
                  {syncResult.segments.map((seg, idx) => (
                    <li key={`${seg.start_before}-${seg.start_after}-${idx}`}>
                      <button
                        type="button"
                        className="w-full text-left px-2 py-1.5 hover:bg-dv-surface text-[10px]"
                        onClick={() => onSegmentClick(seg)}
                        title="Перейти к началу сегмента на обоих Viewer"
                      >
                        Сегмент {idx + 1}: {formatRange(seg.start_before, seg.end_before)}{' '}
                        (Было) ↔ {formatRange(seg.start_after, seg.end_after)} (Стало) ·{' '}
                        {seg.pair_count} пар
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}
      </div>
    </Modal>
  );
};

export default CompareSyncModal;
