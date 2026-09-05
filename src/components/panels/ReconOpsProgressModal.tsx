/** In-panel 3D operations progress modal + minimize chip (Flight3D only). */
import React, { useState } from 'react';
import type { OpsStep } from '../../hooks/useReconOpsProgress';

type Props = {
  visible: boolean;
  minimized: boolean;
  finishing: boolean;
  isError: boolean;
  title: string;
  /** Optional hint under title (e.g. COLMAP → AliceVision). */
  subtitle?: string | null;
  jobId: string | null;
  steps: OpsStep[];
  progressPct: number;
  elapsedSec: number;
  logLines: string[];
  errorMessage: string | null;
  currentLabel?: string;
  onMinimize: () => void;
  onRestore: () => void;
  onCloseError: () => void;
  onRetry: () => void;
};

function statusGlyph(s: OpsStep['status']): string {
  if (s === 'done') return '✓';
  if (s === 'running') return '…';
  if (s === 'error') return '!';
  return '○';
}

function fmtDur(ms?: number): string {
  if (ms == null) return '';
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}с`;
  return `${Math.floor(sec / 60)}м ${sec % 60}с`;
}

export function ReconOpsProgressModal(props: Props) {
  const {
    visible,
    minimized,
    finishing,
    isError,
    title,
    subtitle,
    jobId,
    steps,
    progressPct,
    elapsedSec,
    logLines,
    errorMessage,
    currentLabel,
    onMinimize,
    onRestore,
    onCloseError,
    onRetry,
  } = props;
  const [logsOpen, setLogsOpen] = useState(false);

  if (!visible) return null;

  if (minimized) {
    const chipClass = isError
      ? 'border-red-600 bg-red-950/90 text-red-200'
      : finishing
        ? 'border-emerald-600 bg-emerald-950/90 text-emerald-200'
        : 'border-[var(--dv-accent)] bg-black/85 text-[var(--dv-text)]';
    return (
      <button
        type="button"
        className={`absolute bottom-3 right-3 z-30 max-w-[90%] px-2.5 py-1.5 rounded-sm border text-[11px] font-mono shadow-lg ${chipClass}`}
        onClick={onRestore}
        title="Развернуть прогресс 3D"
      >
        {isError ? (
          <span>Ошибка · {currentLabel || 'шаг'} · нажмите</span>
        ) : finishing ? (
          <span>Готово</span>
        ) : (
          <span>
            ⟳ {currentLabel || '…'} · {progressPct}%
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="absolute inset-0 z-30 flex items-start justify-center pt-8 pointer-events-none">
      <div
        className="pointer-events-auto w-[min(420px,92%)] max-h-[85%] overflow-auto rounded-sm border border-[var(--dv-border)] bg-[var(--dv-bg-deep)]/95 shadow-xl text-[11px]"
        role="dialog"
        aria-label={title}
      >
        <div className="flex items-start justify-between gap-2 px-3 py-2 border-b border-[var(--dv-border)]">
          <div>
            <div className="font-semibold text-[var(--dv-text)]">
              {finishing ? (title.startsWith('Готово') ? title : 'Готово') : title}
            </div>
            {subtitle && !finishing && (
              <div className="text-[10px] text-amber-200/90 mt-0.5 leading-snug">{subtitle}</div>
            )}
            <div className="font-mono text-[var(--dv-text-muted)] mt-0.5">
              {jobId ? `job ${jobId}` : 'job —'} · {elapsedSec}с · {progressPct}%
            </div>
          </div>
          {!isError && !finishing && (
            <button
              type="button"
              className="px-1.5 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] rounded-sm shrink-0"
              onClick={onMinimize}
            >
              Свернуть в фон
            </button>
          )}
        </div>

        <div className="px-3 py-2">
          <div className="h-1.5 bg-[var(--dv-surface)] rounded-sm overflow-hidden mb-2">
            <div
              className={`h-full transition-all ${isError ? 'bg-red-500' : finishing ? 'bg-emerald-500' : 'bg-[var(--dv-accent)]'}`}
              style={{ width: `${progressPct}%` }}
            />
          </div>

          <ul className="flex flex-col gap-1">
            {steps.map((step) => {
              const expanded = step.status === 'running' || step.status === 'error';
              return (
                <li
                  key={step.id}
                  className={`rounded-sm px-2 py-1 border ${
                    step.status === 'error'
                      ? 'border-red-700/60 bg-red-950/30'
                      : step.status === 'running'
                        ? 'border-[var(--dv-accent)]/40 bg-[var(--dv-surface)]/40'
                        : 'border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={
                        step.status === 'done'
                          ? 'text-emerald-400'
                          : step.status === 'error'
                            ? 'text-red-400'
                            : step.status === 'running'
                              ? 'text-[var(--dv-accent)]'
                              : 'text-[var(--dv-text-muted)]'
                      }
                    >
                      {statusGlyph(step.status)}
                    </span>
                    <span className="flex-1">{step.label}</span>
                    {step.durationMs != null && step.status === 'done' && (
                      <span className="font-mono text-[var(--dv-text-muted)]">{fmtDur(step.durationMs)}</span>
                    )}
                  </div>
                  {expanded && step.detail && (
                    <div className="mt-1 font-mono text-[10px] text-[var(--dv-text-muted)] pl-5">{step.detail}</div>
                  )}
                </li>
              );
            })}
          </ul>

          {logLines.length > 0 && (
            <div className="mt-2 border-t border-[var(--dv-border)] pt-1">
              <button
                type="button"
                className="text-[var(--dv-text-muted)] hover:text-[var(--dv-text)]"
                onClick={() => setLogsOpen((v) => !v)}
              >
                {logsOpen ? '▾' : '▸'} Лог ({logLines.length})
              </button>
              {logsOpen && (
                <pre className="mt-1 max-h-24 overflow-auto font-mono text-[9px] text-[var(--dv-text-muted)] whitespace-pre-wrap">
                  {logLines.join('\n')}
                </pre>
              )}
            </div>
          )}

          {isError && (
            <div className="mt-2 flex flex-col gap-1.5">
              {errorMessage && (
                <div className="text-red-300 text-[10px]">{errorMessage}</div>
              )}
              <div className="flex gap-2">
                <button
                  type="button"
                  className="px-2 py-0.5 bg-[var(--dv-surface)] hover:bg-[var(--dv-hover)] rounded-sm"
                  onClick={onCloseError}
                >
                  Закрыть
                </button>
                <button
                  type="button"
                  className="px-2 py-0.5 bg-[var(--dv-accent)] text-black rounded-sm"
                  onClick={onRetry}
                >
                  Повторить
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default ReconOpsProgressModal;
