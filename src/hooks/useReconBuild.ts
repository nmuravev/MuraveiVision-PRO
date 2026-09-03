import { useCallback, useEffect, useRef } from 'react';
import { readSse } from '../lib/readSse';
import { authHeaders } from '../store/useMuraveiStore';
import { useReconStore, type ReconManifest } from '../store/useReconStore';

const MAX_SEGMENT_SEC = 120;

export function computeReconSegment(
  anchorSec: number,
  mediaDuration: number,
): { tStart: number; tEnd: number } {
  let tStart = Math.max(0, anchorSec - 10);
  let tEnd = tStart + MAX_SEGMENT_SEC;
  if (mediaDuration > 0) {
    tEnd = Math.min(tEnd, mediaDuration);
    if (tEnd - tStart > MAX_SEGMENT_SEC) {
      tEnd = tStart + MAX_SEGMENT_SEC;
    }
    if (anchorSec > tEnd - 5) {
      tEnd = Math.min(mediaDuration, anchorSec + 10);
      tStart = Math.max(0, tEnd - MAX_SEGMENT_SEC);
    }
  }
  return { tStart, tEnd };
}

export function isReconReady(manifest: ReconManifest | null | undefined): boolean {
  const st = manifest?.status;
  return st === 'colmap_done' || st === 'done';
}

export function useReconBuild(sourcePath: string | null | undefined, isAuthenticated: boolean) {
  const manifest = useReconStore((s) => s.manifest);
  const reconMessage = useReconStore((s) => s.reconMessage);
  const reconProgress = useReconStore((s) => s.reconProgress);
  const reconRunning = useReconStore((s) => s.reconRunning);
  const setReconProgress = useReconStore((s) => s.setReconProgress);
  const setManifest = useReconStore((s) => s.setManifest);
  const setViewMode = useReconStore((s) => s.setViewMode);
  const streamAbortRef = useRef<AbortController | null>(null);

  const loadManifest = useCallback(async (): Promise<ReconManifest | null> => {
    if (!sourcePath || !isAuthenticated) {
      setManifest(null);
      return null;
    }
    const res = await fetch(`/api/recon/manifest?video_path=${encodeURIComponent(sourcePath)}`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      setManifest(null);
      return null;
    }
    const data = (await res.json()) as {
      manifest?: ReconManifest | null;
      colmap_available?: boolean;
    };
    const man = data.manifest ?? null;
    setManifest(man, Boolean(data.colmap_available));
    return man;
  }, [sourcePath, isAuthenticated, setManifest]);

  const attachStream = useCallback(
    (openSceneOnDone = false) => {
      streamAbortRef.current?.abort();
      const abort = new AbortController();
      streamAbortRef.current = abort;

      void readSse(
        '/api/recon/stream',
        (data) => {
          const running = data.status === 'running';
          const progress = Math.min(1, Math.max(0, Number(data.progress ?? 0)));
          const phase = typeof data.phase === 'string' ? data.phase : null;
          setReconProgress(String(data.message || ''), progress, running, phase);
          if (
            data.status === 'done' ||
            data.status === 'colmap_done' ||
            data.status === 'error' ||
            data.status === 'idle'
          ) {
            abort.abort();
            const done = data.status === 'done' || data.status === 'colmap_done';
            setReconProgress(
              String(data.message || (done ? 'Готово' : 'Остановлено')),
              done ? 1 : progress,
              false,
              done ? 'done' : data.status === 'error' ? 'error' : null,
            );
            void loadManifest();
            if (done && openSceneOnDone) setViewMode('scene');
          }
        },
        abort,
      ).catch(async () => {
        if (abort.signal.aborted) return;
        try {
          const stRes = await fetch('/api/recon/status', { headers: authHeaders() });
          if (!stRes.ok) {
            setReconProgress('Поток SSE прерван', useReconStore.getState().reconProgress, false, null);
            return;
          }
          const st = (await stRes.json()) as {
            status?: string;
            message?: string;
            progress?: number;
            phase?: string;
          };
          const done = st.status === 'colmap_done' || st.status === 'done';
          setReconProgress(
            st.message || (done ? 'Готово' : 'Поток SSE прерван'),
            done ? 1 : Math.min(1, Number(st.progress ?? 0)),
            false,
            st.phase || null,
          );
          if (done) {
            void loadManifest();
            if (openSceneOnDone) setViewMode('scene');
          }
        } catch {
          setReconProgress('Поток SSE прерван', useReconStore.getState().reconProgress, false, null);
        }
      });
    },
    [loadManifest, setReconProgress, setViewMode],
  );

  const startRecon = useCallback(
    async (opts?: {
      tStart?: number;
      tEnd?: number;
      fpsSample?: number;
      openSceneOnDone?: boolean;
    }) => {
      if (!sourcePath || useReconStore.getState().reconRunning) return;
      setReconProgress('Запуск реконструкции…', 0, true, 'starting');
      try {
        const res = await fetch('/api/recon/start', {
          method: 'POST',
          headers: { ...authHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            video_path: sourcePath,
            t_start: opts?.tStart,
            t_end: opts?.tEnd,
            fps_sample: opts?.fpsSample ?? 1,
          }),
        });
        if (!res.ok) {
          const err = (await res.json().catch(() => ({}))) as { detail?: string };
          const detail = err.detail || res.statusText;
          if (String(detail).includes('уже выполняется')) {
            const stRes = await fetch('/api/recon/status', { headers: authHeaders() });
            if (stRes.ok) {
              const st = (await stRes.json()) as {
                status?: string;
                message?: string;
                progress?: number;
                phase?: string;
              };
              if (st.status === 'running') {
                setReconProgress(
                  st.message || 'Выполняется…',
                  Number(st.progress ?? 0),
                  true,
                  st.phase || 'running',
                );
                attachStream(Boolean(opts?.openSceneOnDone));
                return;
              }
            }
            setReconProgress('', 0, false, null);
            void loadManifest();
            return;
          }
          throw new Error(detail);
        }
        attachStream(Boolean(opts?.openSceneOnDone));
      } catch (err) {
        setReconProgress(err instanceof Error ? err.message : 'Ошибка recon', 0, false, 'error');
      }
    },
    [sourcePath, setReconProgress, attachStream, loadManifest],
  );

  const stopRecon = useCallback(async () => {
    streamAbortRef.current?.abort();
    await fetch('/api/recon/stop', { method: 'POST', headers: authHeaders() });
    setReconProgress('Остановка…', useReconStore.getState().reconProgress, false, null);
  }, [setReconProgress]);

  useEffect(() => {
    if (!isAuthenticated || !sourcePath) return;
    let cancelled = false;
    void (async () => {
      await loadManifest();
      const stRes = await fetch('/api/recon/status', { headers: authHeaders() });
      if (cancelled || !stRes.ok) return;
      const st = (await stRes.json()) as {
        status?: string;
        message?: string;
        progress?: number;
        phase?: string;
      };
      if (st.status === 'running') {
        setReconProgress(
          st.message || 'Выполняется…',
          Number(st.progress ?? 0),
          true,
          st.phase || 'running',
        );
        attachStream(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, sourcePath, loadManifest, attachStream, setReconProgress]);

  useEffect(
    () => () => {
      streamAbortRef.current?.abort();
    },
    [],
  );

  const pct = Math.min(100, Math.max(0, Math.round(reconProgress * 100)));

  return {
    manifest,
    hasRecon: isReconReady(manifest),
    reconMessage,
    reconProgress,
    reconRunning,
    pct,
    startRecon,
    stopRecon,
    loadManifest,
  };
}
