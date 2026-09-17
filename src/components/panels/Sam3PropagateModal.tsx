import React, { useEffect } from 'react';
import { Modal, Button } from '../ui';
import {
  useSam3Store,
  type Sam3PropFrame,
  type Sam3Mask,
} from '../../store/useSam3Store';

export type Sam3PropagateModalProps = {
  open: boolean;
  videoPath: string;
  timeSec: number;
  onClose: () => void;
  onPickFrame: (timeSec: number, masks: Sam3Mask[]) => void;
};

export const Sam3PropagateModal: React.FC<Sam3PropagateModalProps> = ({
  open,
  videoPath,
  timeSec,
  onClose,
  onPickFrame,
}) => {
  const persistEnabled = useSam3Store((s) => s.persistEnabled);
  const setPersistEnabled = useSam3Store((s) => s.setPersistEnabled);
  const fullVideoEnabled = useSam3Store((s) => s.fullVideoEnabled);  // P3.13.3d: P1
  const setFullVideoEnabled = useSam3Store((s) => s.setFullVideoEnabled);  // P3.13.3d: P1
  const lastPrompt = useSam3Store((s) => s.lastPrompt);
  const status = useSam3Store((s) => s.propStatus);
  const progress = useSam3Store((s) => s.propProgress);
  const processed = useSam3Store((s) => s.propProcessed);
  const sampleTotal = useSam3Store((s) => s.propSampleTotal);
  const maskTotal = useSam3Store((s) => s.propMaskTotal);
  const persisted = useSam3Store((s) => s.propPersisted);
  const message = useSam3Store((s) => s.propMessage);
  const error = useSam3Store((s) => s.propError);
  const frames = useSam3Store((s) => s.propFrames);
  const totalWindows = useSam3Store((s) => s.propTotalWindows);  // P3.13.3d
  const currentWindow = useSam3Store((s) => s.propCurrentWindow);  // P3.13.3d
  const startPropagate = useSam3Store((s) => s.startPropagate);
  const abortPropagate = useSam3Store((s) => s.abortPropagate);
  const clearPropagate = useSam3Store((s) => s.clearPropagate);

  useEffect(() => {
    if (!open) return;
    clearPropagate();
  }, [open, clearPropagate]);

  const running = status === 'running';
  const pct = Math.round(Math.min(1, Math.max(0, progress)) * 100);
  const hasVisual = Boolean(lastPrompt?.points?.length || lastPrompt?.bboxes?.length);
  const hasText = Boolean(lastPrompt?.text?.length);
  const hasPrompt = hasVisual || hasText;
  const seedLabel = hasText
    ? `text: ${(lastPrompt?.text || []).join('; ')}`
    : hasVisual
      ? `visual: ${lastPrompt?.points?.length || 0} pts / ${lastPrompt?.bboxes?.length || 0} bbox`
      : '';

  const onStart = () => {
    void startPropagate({
      videoPath,
      timeSec,
      maxFrames: 30,
      persist: persistEnabled,
      fullVideo: fullVideoEnabled,  // P3.13.3d: P1
    });
  };

  const onFrameClick = (frame: Sam3PropFrame) => {
    onPickFrame(frame.time_sec, frame.masks || []);
    onClose();
  };

  return (
    <Modal
      open={open}
      wide
      title="SAM3 propagate"
      onClose={() => {
        if (running) void abortPropagate();
        onClose();
      }}
      footer={
        <>
          {running ? (
            <Button size="sm" variant="danger" onClick={() => void abortPropagate()}>
              Отменить
            </Button>
          ) : (
            <Button
              size="sm"
              variant="primary"
              disabled={!videoPath || !hasPrompt}
              onClick={onStart}
              data-testid="sam3-prop-start"
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
      <div className="space-y-3 text-xs text-dv-text" data-testid="sam3-prop-modal">
        <p className="text-[10px] text-dv-muted font-mono truncate" title={videoPath}>
          {videoPath || 'нет видео'} · t={timeSec.toFixed(2)}с · вперёд ≤30 кадров
        </p>
        {!hasPrompt ? (
          <p className="text-[10px] text-dv-danger">
            Сначала точка, «SAM из детекции» или «По тексту» на текущем кадре
          </p>
        ) : (
          <p className="text-[10px] text-dv-muted font-mono" data-testid="sam3-prop-seed">
            seed · {seedLabel}
          </p>
        )}

        <label className="flex items-center gap-2 text-[10px]">
          <input
            type="checkbox"
            checked={persistEnabled}
            disabled={running}
            onChange={(e) => setPersistEnabled(e.target.checked)}
            data-testid="sam3-prop-persist"
          />
          <span>В SQLite (seg_masks, не detections)</span>
        </label>

        <label className="flex items-center gap-2 text-[10px]">
          <input
            type="checkbox"
            checked={fullVideoEnabled}
            disabled={running}
            onChange={(e) => setFullVideoEnabled(e.target.checked)}
            data-testid="sam3-prop-full-video"
          />
          <span>Полное видео (чанки ≤30 кадров)</span>
        </label>

        {fullVideoEnabled && (
          <p className="text-[10px] text-dv-muted">
            Полное видео для 9-мин клипа ≈ 6–12 мин на CPU
          </p>
        )}

        {(running || status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            <div className="h-2 bg-dv-deep border border-dv-border rounded-sm overflow-hidden">
              <div
                className="h-full bg-dv-accent transition-all"
                style={{ width: `${pct}%` }}
                data-testid="sam3-prop-progress"
              />
            </div>
            <div className="text-[10px] text-dv-muted font-mono">
              {pct}% · {processed}/{sampleTotal || '—'} · масок {maskTotal}
              {persisted > 0 ? ` · SQLite ${persisted}` : ''}
              {totalWindows > 0 && (
                <span className="ml-2">Окно {currentWindow}/{totalWindows}</span>
              )}
            </div>
          </div>
        )}

        {message ? <p className="text-[10px] text-dv-muted">{message}</p> : null}
        {error ? (
          <p className="text-[10px] text-dv-danger" data-testid="sam3-prop-error">
            {error}
          </p>
        ) : null}

        {(status === 'done' || status === 'aborted') && (
          <div className="space-y-1">
            <p className="text-[11px]" data-testid="sam3-prop-summary">
              Обработано {processed} кадров, найдено {maskTotal} масок
              {persisted > 0 ? `, записано ${persisted}` : ''}
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

export default Sam3PropagateModal;
