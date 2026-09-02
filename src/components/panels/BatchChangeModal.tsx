import React, { useEffect, useState } from 'react';
import { Modal, Button } from '../ui';
import {
  useBatchChangeStore,
  type BatchChangePairResult,
} from '../../store/useBatchChangeStore';
import {
  useChangeDetectionStore,
  type ChangeDetectionResult,
} from '../../store/useChangeDetectionStore';

export type BatchChangeModalProps = {
  open: boolean;
  videoBefore: string;
  videoAfter: string;
  onClose: () => void;
};

function pairToResult(pair: BatchChangePairResult): ChangeDetectionResult {
  return {
    method: pair.method || 'none',
    aligned: Boolean(pair.aligned),
    message: pair.message ?? null,
    summary: pair.summary,
    matches: pair.matches || [],
    new: pair.new || [],
    removed: pair.removed || [],
    image_diff: pair.image_diff ?? null,
  };
}

export const BatchChangeModal: React.FC<BatchChangeModalProps> = ({
  open,
  videoBefore,
  videoAfter,
  onClose,
}) => {
  const [pairStride, setPairStride] = useState(1);
  const [maxPairs, setMaxPairs] = useState(50);
  const [useImageFallback, setUseImageFallback] = useState(false);

  const status = useBatchChangeStore((s) => s.status);
  const progress = useBatchChangeStore((s) => s.progress);
  const processed = useBatchChangeStore((s) => s.processed);
  const sampleTotal = useBatchChangeStore((s) => s.sampleTotal);
  const message = useBatchChangeStore((s) => s.message);
  const error = useBatchChangeStore((s) => s.error);
  const pairs = useBatchChangeStore((s) => s.pairs);
  const aggregate = useBatchChangeStore((s) => s.aggregate);
  const exportBusy = useBatchChangeStore((s) => s.exportBusy);
  const exportError = useBatchChangeStore((s) => s.exportError);
  const startBatch = useBatchChangeStore((s) => s.startBatch);
  const abortBatch = useBatchChangeStore((s) => s.abortBatch);
  const exportHtml = useBatchChangeStore((s) => s.exportHtml);
  const clear = useBatchChangeStore((s) => s.clear);

  const applyPairResult = useChangeDetectionStore((s) => s.applyPairResult);
  const requestSeek = useChangeDetectionStore((s) => s.requestSeek);

  useEffect(() => {
    if (!open) return;
    clear();
    setPairStride(1);
    setMaxPairs(50);
    setUseImageFallback(false);
  }, [open, clear]);

  const running = status === 'running';
  const pct = Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const canStart = Boolean(videoBefore && videoAfter);

  const onStart = () => {
    void startBatch({
      videoBefore,
      videoAfter,
      pairStride,
      maxPairs,
      useImageFallback,
    });
  };

  const onPairClick = (pair: BatchChangePairResult) => {
    applyPairResult(pairToResult(pair), {
      videoBefore,
      videoAfter,
      timeBefore: pair.time_before,
      timeAfter: pair.time_after,
      timeWindowSec: 0.5,
    });
    requestSeek(pair.time_before, pair.time_after);
    onClose();
  };

  return (
    <Modal
      open={open}
      wide
      title="Пакетный Change Detection"
      onClose={() => {
        if (running) void abortBatch();
        onClose();
      }}
      footer={
        <>
          {running ? (
            <Button size="sm" variant="danger" onClick={() => void abortBatch()}>
              Отменить
            </Button>
          ) : (
            <Button size="sm" variant="primary" disabled={!canStart} onClick={onStart}>
              Старт
            </Button>
          )}
          {status === 'done' ? (
            <Button
              size="sm"
              disabled={exportBusy}
              onClick={() => void exportHtml()}
            >
              {exportBusy ? 'Экспорт…' : 'Экспорт HTML'}
            </Button>
          ) : null}
          <Button size="sm" onClick={onClose}>
            Закрыть
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-xs text-dv-text" data-testid="batch-change-modal">
        <p className="text-[10px] text-dv-muted font-mono truncate" title={videoBefore}>
          Было: {videoBefore || '—'}
        </p>
        <p className="text-[10px] text-dv-muted font-mono truncate" title={videoAfter}>
          Стало: {videoAfter || '—'}
        </p>

        <label className="block space-y-1">
          <span className="dv-section-label">Stride пар: {pairStride}</span>
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={pairStride}
            disabled={running}
            onChange={(e) => setPairStride(Number(e.target.value))}
            className="w-full"
            data-testid="batch-change-stride"
          />
        </label>

        <label className="block space-y-1">
          <span className="dv-section-label">Макс. пар: {maxPairs}</span>
          <input
            type="range"
            min={5}
            max={200}
            step={5}
            value={maxPairs}
            disabled={running}
            onChange={(e) => setMaxPairs(Number(e.target.value))}
            className="w-full"
            data-testid="batch-change-max-pairs"
          />
        </label>

        <label className="flex items-center gap-2 text-[11px]">
          <input
            type="checkbox"
            checked={useImageFallback}
            disabled={running}
            onChange={(e) => setUseImageFallback(e.target.checked)}
            data-testid="batch-change-orb"
          />
          ORB / image fallback (медленнее)
        </label>

        {(running || status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            <div className="h-2 bg-dv-deep border border-dv-border rounded-sm overflow-hidden">
              <div
                className="h-full bg-dv-accent transition-all"
                style={{ width: `${pct}%` }}
                data-testid="batch-change-progress"
              />
            </div>
            <div className="text-[10px] text-dv-muted font-mono">
              {pct}% · {processed}/{sampleTotal || '—'}
            </div>
          </div>
        )}

        {message ? <p className="text-[10px] text-dv-muted">{message}</p> : null}
        {error ? <p className="text-[10px] text-dv-danger">{error}</p> : null}
        {exportError ? <p className="text-[10px] text-dv-danger">{exportError}</p> : null}

        {(status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            {aggregate ? (
              <p className="text-[11px]" data-testid="batch-change-summary">
                Уник. +{aggregate.unique_new}/-{aggregate.unique_removed}/↔
                {aggregate.unique_moved} · пар {aggregate.pair_count}
              </p>
            ) : null}
            {pairs.length > 0 ? (
              <ul
                className="max-h-48 overflow-auto space-y-0.5 border border-dv-border p-1"
                data-testid="batch-change-pairs"
              >
                {pairs.map((p) => {
                  const s = p.summary || {
                    new: 0,
                    removed: 0,
                    moved: 0,
                    stable: 0,
                    matched: 0,
                    total_before: 0,
                    total_after: 0,
                  };
                  return (
                    <li key={`${p.time_before}-${p.time_after}`}>
                      <button
                        type="button"
                        className="w-full text-left px-1 py-0.5 text-[10px] font-mono hover:bg-dv-surface rounded-sm"
                        onClick={() => onPairClick(p)}
                      >
                        t={p.time_before.toFixed(1)}с → {p.time_after.toFixed(1)}с: +
                        {s.new}/-{s.removed}/↔{s.moved}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </div>
        )}
      </div>
    </Modal>
  );
};

export default BatchChangeModal;
