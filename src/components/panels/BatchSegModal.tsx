import React, { useEffect, useState } from 'react';
import { Modal, Button } from '../ui';
import {
  useBatchSegStore,
  type BatchSegFrame,
  type BatchSegMask,
} from '../../store/useBatchSegStore';

export type BatchSegModalProps = {
  open: boolean;
  videoPath: string;
  onClose: () => void;
  onPickFrame: (timeSec: number, masks: BatchSegMask[]) => void;
};

export const BatchSegModal: React.FC<BatchSegModalProps> = ({
  open,
  videoPath,
  onClose,
  onPickFrame,
}) => {
  const [frameStep, setFrameStep] = useState(30);
  const [confidence, setConfidence] = useState(0.5);

  const status = useBatchSegStore((s) => s.status);
  const progress = useBatchSegStore((s) => s.progress);
  const processed = useBatchSegStore((s) => s.processed);
  const sampleTotal = useBatchSegStore((s) => s.sampleTotal);
  const maskTotal = useBatchSegStore((s) => s.maskTotal);
  const message = useBatchSegStore((s) => s.message);
  const error = useBatchSegStore((s) => s.error);
  const frames = useBatchSegStore((s) => s.frames);
  const samUnloaded = useBatchSegStore((s) => s.samUnloaded);
  const startBatch = useBatchSegStore((s) => s.startBatch);
  const abortBatch = useBatchSegStore((s) => s.abortBatch);
  const clear = useBatchSegStore((s) => s.clear);

  useEffect(() => {
    if (!open) return;
    clear();
    setFrameStep(30);
    setConfidence(0.5);
  }, [open, clear]);

  const running = status === 'running';
  const pct = Math.round(Math.min(1, Math.max(0, progress)) * 100);

  const onStart = () => {
    void startBatch({ videoPath, frameStep, confidence });
  };

  const onFrameClick = (frame: BatchSegFrame) => {
    onPickFrame(frame.time_sec, frame.masks || []);
    onClose();
  };

  return (
    <Modal
      open={open}
      wide
      title="Batch сегментация"
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
            <Button
              size="sm"
              variant="primary"
              disabled={!videoPath}
              onClick={onStart}
            >
              Старт
            </Button>
          )}
          <Button size="sm" onClick={onClose}>
            Закрыть
          </Button>
        </>
      }
    >
      <div className="space-y-3 text-xs text-dv-text" data-testid="batch-seg-modal">
        <p className="text-[10px] text-dv-muted font-mono truncate" title={videoPath}>
          {videoPath || 'нет видео'}
        </p>

        <label className="block space-y-1">
          <span className="dv-section-label">Шаг кадров: {frameStep}</span>
          <input
            type="range"
            min={10}
            max={120}
            step={1}
            value={frameStep}
            disabled={running}
            onChange={(e) => setFrameStep(Number(e.target.value))}
            className="w-full"
            data-testid="batch-seg-frame-step"
          />
        </label>

        <label className="block space-y-1">
          <span className="dv-section-label">Confidence: {confidence.toFixed(2)}</span>
          <input
            type="range"
            min={0.3}
            max={0.9}
            step={0.05}
            value={confidence}
            disabled={running}
            onChange={(e) => setConfidence(Number(e.target.value))}
            className="w-full"
            data-testid="batch-seg-confidence"
          />
        </label>

        {(running || status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            <div className="h-2 bg-dv-deep border border-dv-border rounded-sm overflow-hidden">
              <div
                className="h-full bg-dv-accent transition-all"
                style={{ width: `${pct}%` }}
                data-testid="batch-seg-progress"
              />
            </div>
            <div className="text-[10px] text-dv-muted font-mono">
              {pct}% · {processed}/{sampleTotal || '—'} · масок {maskTotal}
            </div>
          </div>
        )}

        {message ? <p className="text-[10px] text-dv-muted">{message}</p> : null}
        {samUnloaded ? (
          <p className="text-[10px] text-dv-accent" data-testid="batch-seg-sam-unloaded">
            SAM выгружен для запуска batch сегментации
          </p>
        ) : null}
        {error ? <p className="text-[10px] text-dv-danger">{error}</p> : null}

        {(status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            <p className="text-[11px]" data-testid="batch-seg-summary">
              Обработано {processed} кадров, найдено {maskTotal} масок
            </p>
            {frames.length > 0 ? (
              <ul className="max-h-40 overflow-auto space-y-0.5 border border-dv-border p-1">
                {frames.map((f) => (
                  <li key={`${f.time_sec}-${f.masks.length}`}>
                    <button
                      type="button"
                      className="w-full text-left px-1 py-0.5 text-[10px] font-mono hover:bg-dv-surface rounded-sm"
                      onClick={() => onFrameClick(f)}
                    >
                      t={f.time_sec.toFixed(1)}с · {f.masks.length} masks
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}
      </div>
    </Modal>
  );
};

export default BatchSegModal;
