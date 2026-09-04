import { useCallback, useEffect, useRef } from 'react';
import { addEvent } from '../debug/sessionTrace';
import { readSse } from '../lib/readSse';
import { SILENT_API_ERROR_HEADER } from '../lib/apiError';
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

/** Single RU phrase for OpsStatusBar / SSE terminal — sparse ≠ Gaussian splat. */
export function reconTerminalLabel(
  status: string | null | undefined,
  error?: string | null,
): string {
  if (status === 'error') return error || 'ошибка';
  if (status === 'done') return 'готово · Gaussian splat';
  if (status === 'colmap_done') return 'sparse COLMAP · нужен train для splat';
  return status || '';
}

function reconProgressMeta(data: {
  job_id?: unknown;
  stage?: unknown;
}): { jobId?: string | null; stage?: string | null } {
  const meta: { jobId?: string | null; stage?: string | null } = {};
  if (typeof data.job_id === 'string' && data.job_id) meta.jobId = data.job_id;
  if (typeof data.stage === 'string') meta.stage = data.stage;
  else if (data.stage === null) meta.stage = null;
  return meta;
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
  const startInFlightRef = useRef(false);
  const tracedInlineSkipRef = useRef<string | null>(null);

  const noteInlineGsplatSkipped = useCallback((man: ReconManifest | null) => {
    if (!man?.job_id) return;
    if (man.status !== 'colmap_done' || man.artifact) return;
    if (
      man.next_action != null &&
      man.next_action !== 'balanced_for_splat'
    ) {
      return;
    }
    if (tracedInlineSkipRef.current === man.job_id) return;
    tracedInlineSkipRef.current = man.job_id;
    addEvent('note', 'gsplat-inline-skipped', { job_id: man.job_id });
  }, []);

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
    noteInlineGsplatSkipped(man);
    return man;
  }, [sourcePath, isAuthenticated, setManifest, noteInlineGsplatSkipped]);

  const attachStream = useCallback(
    (openSceneOnDone = false) => {
      streamAbortRef.current?.abort();
      const abort = new AbortController();
      streamAbortRef.current = abort;

      void readSse(
        '/api/recon/stream',
        (data) => {
          const status = typeof data.status === 'string' ? data.status : null;
          const terminal =
            status === 'done' ||
            status === 'colmap_done' ||
            status === 'error' ||
            status === 'idle';
          // Progress-only SSE events omit status — must NOT clear reconRunning
          const running = status === 'running' || (!terminal && status == null && useReconStore.getState().reconRunning);
          const progress = Math.min(
            1,
            Math.max(0, Number(data.progress ?? useReconStore.getState().reconProgress ?? 0)),
          );
          const phase =
            typeof data.phase === 'string' ? data.phase : useReconStore.getState().reconPhase;
          const meta = reconProgressMeta(data);
          setReconProgress(String(data.message || ''), progress, running, phase, meta);
          if (terminal) {
            abort.abort();
            const done = status === 'done' || status === 'colmap_done';
            const terminalMsg = done
              ? reconTerminalLabel(status)
              : status === 'error'
                ? String(data.message || 'ошибка')
                : 'Остановлено';
            setReconProgress(
              terminalMsg,
              done ? 1 : progress,
              false,
              done ? 'done' : status === 'error' ? 'error' : null,
              meta,
            );
            useReconStore.setState({ lastReconMessage: terminalMsg });
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
            job_id?: string;
            stage?: string;
          };
          const meta = reconProgressMeta(st);
          if (st.status === 'running') {
            // Job still alive — keep busy and re-attach; never clear reconRunning
            setReconProgress(
              st.message || 'Выполняется…',
              Math.min(1, Number(st.progress ?? 0)),
              true,
              st.phase || 'running',
              meta,
            );
            if (streamAbortRef.current === abort) {
              attachStream(openSceneOnDone);
            }
            return;
          }
          const done = st.status === 'colmap_done' || st.status === 'done';
          setReconProgress(
            st.message ||
              (done
                ? reconTerminalLabel(st.status)
                : 'Поток SSE прерван'),
            done ? 1 : Math.min(1, Number(st.progress ?? 0)),
            false,
            st.phase || null,
            meta,
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
      const st0 = useReconStore.getState();
      if (!sourcePath || st0.reconRunning || startInFlightRef.current) return;
      startInFlightRef.current = true;
      setReconProgress('Запуск реконструкции…', 0, true, 'starting', {
        jobId: null,
        stage: null,
      });
      try {
        const res = await fetch('/api/recon/start', {
          method: 'POST',
          headers: {
            ...authHeaders(),
            'Content-Type': 'application/json',
            [SILENT_API_ERROR_HEADER]: '1',
          },
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
          if (res.status === 409 || String(detail).includes('уже выполняется')) {
            const stRes = await fetch('/api/recon/status', { headers: authHeaders() });
            if (stRes.ok) {
              const st = (await stRes.json()) as {
                status?: string;
                message?: string;
                progress?: number;
                phase?: string;
                job_id?: string;
                stage?: string;
              };
              if (st.status === 'running') {
                setReconProgress(
                  st.message || 'Выполняется…',
                  Number(st.progress ?? 0),
                  true,
                  st.phase || 'running',
                  reconProgressMeta(st),
                );
                attachStream(Boolean(opts?.openSceneOnDone));
                return;
              }
            }
            setReconProgress('', 0, false, null, { jobId: null, stage: null });
            void loadManifest();
            return;
          }
          throw new Error(detail);
        }
        const started = (await res.json().catch(() => ({}))) as {
          job_id?: string;
          message?: string;
          progress?: number;
          phase?: string;
          stage?: string;
        };
        setReconProgress(
          started.message || 'Запуск…',
          Number(started.progress ?? 0),
          true,
          started.phase || 'starting',
          reconProgressMeta(started),
        );
        attachStream(Boolean(opts?.openSceneOnDone));
      } catch (err) {
        setReconProgress(err instanceof Error ? err.message : 'Ошибка recon', 0, false, 'error');
      } finally {
        startInFlightRef.current = false;
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
      if (cancelled) return;
      // Disk already ready — never keep ghost COLMAP modal from a dead SSE/job
      const man = useReconStore.getState().manifest;
      if (isReconReady(man) && useReconStore.getState().reconRunning) {
        setReconProgress(
          reconTerminalLabel(man?.status),
          1,
          false,
          'done',
        );
        return;
      }
      const stRes = await fetch('/api/recon/status', { headers: authHeaders() });
      if (cancelled || !stRes.ok) return;
      const st = (await stRes.json()) as {
        status?: string;
        message?: string;
        progress?: number;
        phase?: string;
        job_id?: string;
        stage?: string;
      };
      if (st.status === 'running') {
        // Ignore in-memory "running" if disk manifest for this video is already done
        const man2 = useReconStore.getState().manifest;
        if (isReconReady(man2)) {
          setReconProgress(reconTerminalLabel(man2?.status), 1, false, 'done');
          return;
        }
        setReconProgress(
          st.message || 'Выполняется…',
          Number(st.progress ?? 0),
          true,
          st.phase || 'running',
          reconProgressMeta(st),
        );
        attachStream(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, sourcePath, loadManifest, attachStream, setReconProgress]);

  // Clear ghost busy if manifest flips to ready while modal still shows COLMAP
  useEffect(() => {
    if (!isReconReady(manifest)) return;
    if (!useReconStore.getState().reconRunning) return;
    setReconProgress(reconTerminalLabel(manifest?.status), 1, false, 'done');
  }, [manifest?.status, manifest?.job_id, setReconProgress]);

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
