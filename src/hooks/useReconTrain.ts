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

  const refreshPresets = useCallback(async () => {
    if (!isAuthenticated) return;
    const res = await fetch('/api/recon/train/presets', { headers: authHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as { presets?: TrainPreset[]; colmap_running?: boolean };
    setPresets(data.presets || []);
    setColmapRunning(Boolean(data.colmap_running));
  }, [isAuthenticated]);

  const refreshStatus = useCallback(async () => {
    if (!isAuthenticated) return;
    const res = await fetch('/api/recon/train/status', { headers: authHeaders() });
    if (!res.ok) return;
    const st = (await res.json()) as TrainStatus;
    setTrain(st);
    setColmapRunning(Boolean(st.colmap_running));
  }, [isAuthenticated]);

  const attachStream = useCallback(
    (onDone?: () => void) => {
      streamAbortRef.current?.abort();
      clearPoll();
      const abort = new AbortController();
      streamAbortRef.current = abort;

      const apply = (data: Record<string, unknown>) => {
        const st = data as unknown as TrainStatus;
        setTrain(st);
        if (st.status === 'done' || st.status === 'error' || st.status === 'idle') {
          abort.abort();
          clearPoll();
          if (st.status === 'done') onDone?.();
        }
      };

      void readSse('/api/recon/train/stream', apply, abort).catch(() => {
        if (abort.signal.aborted) return;
        // Fallback poll every 3s
        void refreshStatus();
        pollRef.current = setInterval(() => {
          void (async () => {
            const res = await fetch('/api/recon/train/status', { headers: authHeaders() });
            if (!res.ok) return;
            const st = (await res.json()) as TrainStatus;
            setTrain(st);
            if (st.status === 'done' || st.status === 'error' || st.status === 'idle') {
              clearPoll();
              if (st.status === 'done') onDone?.();
            }
          })();
        }, 3000);
      });
    },
    [refreshStatus],
  );

  const startTrain = useCallback(
    async (preset: string, onDone?: () => void) => {
      if (!jobId || startInFlightRef.current) return;
      if (colmapRunning || train.status === 'training') return;
      startInFlightRef.current = true;
      setTrain((s) => ({ ...s, status: 'training', message: 'Запуск…', error: null, preset }));
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
    [jobId, colmapRunning, train.status, attachStream],
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
    train,
    training,
    colmapRunning,
    startTrain,
    stopTrain,
    refreshPresets,
    refreshStatus,
  };
}
