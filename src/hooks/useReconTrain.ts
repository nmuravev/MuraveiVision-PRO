/** Hook: gsplat/bootstrap train presets for Flight3D Scene tab. */
import { useCallback, useEffect, useRef, useState } from 'react';
import { readSse } from '../lib/readSse';
import { SILENT_API_ERROR_HEADER } from '../lib/apiError';
import { authHeaders } from '../store/useMuraveiStore';

export type TrainPreset = {
  id: string;
  label: string;
  eta: string;
  default?: boolean;
  disabled: boolean;
  disabled_reason: string;
  alias_of?: string | null;
  backend?: string | null;
};

export type TrainStatus = {
  status: string;
  job_id?: string | null;
  preset?: string | null;
  steps?: number;
  max_steps?: number;
  loss?: number | null;
  psnr?: number | null;
  vram_used_gb?: number;
  vram_total_gb?: number;
  eta_seconds?: number | null;
  message?: string;
  error?: string | null;
  artifact?: string | null;
  colmap_running?: boolean;
};

export function useReconTrain(jobId: string | null | undefined, isAuthenticated: boolean) {
  const [presets, setPresets] = useState<TrainPreset[]>([]);
  const [presetsError, setPresetsError] = useState<string | null>(null);
  const [train, setTrain] = useState<TrainStatus>({ status: 'idle' });
  const [colmapRunning, setColmapRunning] = useState(false);
  const streamAbortRef = useRef<AbortController | null>(null);
  const startInFlightRef = useRef(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPoll = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const silentHeaders = () => ({
    ...authHeaders(),
    [SILENT_API_ERROR_HEADER]: '1',
  });

  const refreshPresets = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/recon/train/presets', { headers: silentHeaders() });
      if (!res.ok) {
        setPresets([]);
        setPresetsError(
          res.status === 404
            ? 'API обучения недоступен (404). Перезапустите backend.'
            : `Не удалось загрузить профили (${res.status}).`,
        );
        return;
      }
      const data = (await res.json()) as { presets?: TrainPreset[]; colmap_running?: boolean };
      setPresets(data.presets || []);
      setColmapRunning(Boolean(data.colmap_running));
      setPresetsError(null);
    } catch {
      setPresets([]);
      setPresetsError('Не удалось загрузить профили обучения (сеть).');
    }
  }, [isAuthenticated]);

  const refreshStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/recon/train/status', { headers: silentHeaders() });
      if (!res.ok) return;
      const st = (await res.json()) as TrainStatus;
      setTrain(st);
      setColmapRunning(Boolean(st.colmap_running));
    } catch {
      /* ignore */
    }
  }, [isAuthenticated]);

  const attachStream = useCallback(
    (onDone?: () => void) => {
      streamAbortRef.current?.abort();
      clearPoll();
      const abort = new AbortController();
      streamAbortRef.current = abort;

      const apply = (data: Record<string, unknown>) => {
        const st = data as unknown as TrainStatus & {
          event?: string;
          alicevision_step?: string;
        };
        setTrain(st);
        const evName = typeof data.event === 'string' ? data.event : '';
        if (
          evName.startsWith('alicevision') ||
          evName === 'dense-artifact-ready' ||
          evName === 'mesh-artifact-ready'
        ) {
          void import('../debug/sessionTrace').then(({ addEvent }) => {
            addEvent(
              'note',
              `${evName}${st.alicevision_step ? ` · ${st.alicevision_step}` : ''}`,
              {
                event: evName,
                step: st.alicevision_step,
                preset: st.preset,
                job_id: st.job_id,
                message: st.message,
              },
            );
          });
        }
        if (st.status === 'done' || st.status === 'error' || st.status === 'idle') {
          abort.abort();
          clearPoll();
          streamAbortRef.current = null;
          if (st.status === 'done') onDone?.();
        }
      };

      const startStatusPoll = () => {
        if (pollRef.current) return;
        void refreshStatus();
        pollRef.current = setInterval(() => {
          void (async () => {
            const res = await fetch('/api/recon/train/status', {
              headers: { ...authHeaders(), [SILENT_API_ERROR_HEADER]: '1' },
            });
            if (!res.ok) {
              // Backend restart / expired session: unlock stuck «training» modal.
              setTrain((prev) => {
                if (prev.status !== 'training') return prev;
                return {
                  ...prev,
                  status: 'error',
                  error:
                    res.status === 401
                      ? 'Сессия истекла / backend перезапущен — войдите снова и повторите Balanced'
                      : `Нет связи с train status (${res.status}) — backend мог перезапуститься`,
                  message: 'Обучение прервано (потерян статус)',
                };
              });
              clearPoll();
              streamAbortRef.current = null;
              abort.abort();
              return;
            }
            const st = (await res.json()) as TrainStatus;
            setTrain(st);
            if (st.status === 'done' || st.status === 'error' || st.status === 'idle') {
              clearPoll();
              streamAbortRef.current = null;
              abort.abort();
              if (st.status === 'done') onDone?.();
            }
          })();
        }, 3000);
      };

      // Parallel poll: SSE clean-close after uvicorn kill does not reject, so UI
      // would stay on training forever without a status heartbeat.
      startStatusPoll();

      void readSse('/api/recon/train/stream', apply, abort)
        .catch(() => {
          if (abort.signal.aborted) return;
          startStatusPoll();
        })
        .finally(() => {
          if (abort.signal.aborted) return;
          // Stream ended without terminal event (backend restart) — keep polling.
          startStatusPoll();
        });
    },
    [refreshStatus],
  );

  const startTrain = useCallback(
    async (preset: string, onDone?: () => void) => {
      if (!jobId || startInFlightRef.current) {
        if (!jobId) {
          setTrain((s) => ({
            ...s,
            status: 'error',
            error: 'Нет job_id — сначала «Построить 3D»',
            message: 'Обучение не удалось: нет job_id',
          }));
        }
        return;
      }
      if (train.status === 'training') {
        return;
      }
      // Do not hard-block on stale colmapRunning flag — backend rejects if COLMAP truly running.
      // UI already gates via trainBlocked; silent return here made Balanced look dead.
      startInFlightRef.current = true;
      // Do not set status=training before POST succeeds — that attaches SSE which
      // can overwrite a 409 error with idle within ~10ms (looked like "nothing happened").
      setTrain((s) => ({
        ...s,
        message: 'Запуск…',
        error: null,
        preset,
      }));
      try {
        const res = await fetch('/api/recon/train/start', {
          method: 'POST',
          headers: {
            ...authHeaders(),
            'Content-Type': 'application/json',
            [SILENT_API_ERROR_HEADER]: '1',
          },
          body: JSON.stringify({ job_id: jobId, preset }),
        });
        if (!res.ok) {
          streamAbortRef.current?.abort();
          streamAbortRef.current = null;
          const err = (await res.json().catch(() => ({}))) as { detail?: string };
          const detail = err.detail || res.statusText;
          setTrain((s) => ({
            ...s,
            status: 'error',
            error: detail,
            message: `Обучение не удалось: ${detail}`,
          }));
          return;
        }
        const st = (await res.json()) as TrainStatus;
        setTrain(st);
        attachStream(onDone);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Ошибка train';
        setTrain((s) => ({ ...s, status: 'error', error: msg, message: `Обучение не удалось: ${msg}` }));
      } finally {
        startInFlightRef.current = false;
      }
    },
    [jobId, train.status, attachStream],
  );

  const stopTrain = useCallback(async () => {
    streamAbortRef.current?.abort();
    clearPoll();
    await fetch('/api/recon/train/stop', { method: 'POST', headers: authHeaders() });
    await refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void refreshPresets();
    void refreshStatus();
  }, [isAuthenticated, refreshPresets, refreshStatus]);

  useEffect(() => {
    if (train.status === 'training' && !streamAbortRef.current) {
      attachStream();
    }
  }, [train.status, attachStream]);

  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
      clearPoll();
    },
    [],
  );

  const training = train.status === 'training';

  return {
    presets,
    presetsError,
    train,
    training,
    colmapRunning,
    startTrain,
    stopTrain,
    refreshPresets,
    refreshStatus,
  };
}
