/** Derive step-by-step 3D ops progress from recon store + train hook + scene load. */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { addEvent } from '../debug/sessionTrace';
import { useReconStore } from '../store/useReconStore';
import type { TrainStatus } from './useReconTrain';

export type OpsStepStatus = 'pending' | 'running' | 'done' | 'error';

export type OpsStep = {
  id: string;
  label: string;
  status: OpsStepStatus;
  detail?: string;
  durationMs?: number;
};

export const OPS_LOG_CAP = 20;
const AUTO_DISMISS_MS = 1800;
const TRAIN_HOLD_DISMISS_MS = 8000;

/** Ordered COLMAP stages emitted by backend (phase=colmap + stage=…). */
export const COLMAP_STAGE_ORDER = [
  'plan',
  'feature_extractor',
  'matcher',
  'mapper',
  'model_converter',
] as const;

export function normalizeColmapStage(stage: string | null | undefined): string | null {
  if (!stage) return null;
  const s = stage.trim().toLowerCase();
  if (s === 'sequential_matcher' || s === 'exhaustive_matcher') return 'matcher';
  if (s === 'extract_frames') return 'extracting';
  if ((COLMAP_STAGE_ORDER as readonly string[]).includes(s)) return s;
  if (s === 'export_poses' || s === 'colmap_done' || s === 'done') return s;
  return s;
}

export function matcherStepLabel(stage: string | null | undefined): string {
  const raw = (stage || '').toLowerCase();
  if (raw === 'exhaustive_matcher') return 'exhaustive_matcher';
  if (raw === 'sequential_matcher') return 'sequential_matcher';
  return 'matcher';
}

/** Index into COLMAP_STAGE_ORDER; -1 before colmap; 99 after all COLMAP stages. */
export function colmapStageIndex(stage: string | null | undefined, phase: string | null): number {
  const n = normalizeColmapStage(stage);
  if (phase === 'export_poses' || phase === 'done' || phase === 'colmap_done' || phase === 'training') {
    return 99;
  }
  if (n && (COLMAP_STAGE_ORDER as readonly string[]).includes(n)) {
    return COLMAP_STAGE_ORDER.indexOf(n as (typeof COLMAP_STAGE_ORDER)[number]);
  }
  if (phase === 'colmap') return 0;
  return -1;
}

function reconActiveIndex(
  phase: string | null,
  stage: string | null,
  running: boolean,
  loading: boolean,
): number {
  if (loading && !running) return 99; // load_scene after recon
  if (!phase) return running ? 0 : -1;
  if (phase === 'starting' || phase === 'extracting') return 0;
  if (phase === 'colmap') {
    const si = colmapStageIndex(stage, phase);
    return si < 0 ? 1 : 1 + si; // 1=plan … after extracting
  }
  if (phase === 'export_poses') return 1 + COLMAP_STAGE_ORDER.length;
  // phase === 'training' is preset-train / GSPLAT_INLINE only — not a COLMAP modal step
  if (phase === 'training') return -1;
  if (phase === 'done' || phase === 'colmap_done') return loading ? 99 : 100;
  if (phase === 'error') return -2;
  return running ? 0 : -1;
}

export function useReconOpsProgress(opts: {
  training: boolean;
  train: TrainStatus;
  sceneLoading: boolean;
  sceneError: string | null;
  /** After train: hold success chip until splat appears (or timeout). */
  sceneKind?: 'empty' | 'points' | 'splat' | null;
  onRetryRecon?: () => void;
  onRetryTrain?: (preset?: string) => void;
}) {
  const {
    training,
    train,
    sceneLoading,
    sceneError,
    sceneKind = null,
    onRetryRecon,
    onRetryTrain,
  } = opts;
  const reconRunning = useReconStore((s) => s.reconRunning);
  const reconPhase = useReconStore((s) => s.reconPhase);
  const reconStage = useReconStore((s) => s.reconStage);
  const reconProgress = useReconStore((s) => s.reconProgress);
  const reconMessage = useReconStore((s) => s.reconMessage);
  const lastReconMessage = useReconStore((s) => s.lastReconMessage);
  const reconJobId = useReconStore((s) => s.reconJobId);
  const manifest = useReconStore((s) => s.manifest);

  const [minimized, setMinimized] = useState(false);
  const [open, setOpen] = useState(false);
  const [phaseUi, setPhaseUi] = useState<'work' | 'success' | 'error'>('work');
  const [logLines, setLogLines] = useState<string[]>([]);
  const [tick, setTick] = useState(0);

  const startedAtRef = useRef<number | null>(null);
  const opKindRef = useRef<'recon' | 'train' | 'load'>('recon');
  const lastPresetRef = useRef<string | undefined>(undefined);
  const wasBusyRef = useRef(false);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stepStartRef = useRef<Record<string, number>>({});
  const stepDurRef = useRef<Record<string, number>>({});

  const busy = reconRunning || training || sceneLoading;

  useEffect(() => {
    if (!busy && phaseUi !== 'work') return;
    if (!busy) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [busy, phaseUi]);

  useEffect(() => {
    if (!busy) return;
    if (!open) {
      setOpen(true);
      setMinimized(false);
      setPhaseUi('work');
      startedAtRef.current = Date.now();
      stepStartRef.current = {};
      stepDurRef.current = {};
      setLogLines([]);
      addEvent('modal', 'recon-ops open', { reconRunning, training, sceneLoading });
    }
    wasBusyRef.current = true;
    if (reconRunning) opKindRef.current = 'recon';
    else if (training) {
      opKindRef.current = 'train';
      if (train.preset) lastPresetRef.current = train.preset;
    } else if (sceneLoading) opKindRef.current = 'load';
    if (dismissTimerRef.current) {
      clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    }
    setPhaseUi('work');
  }, [busy, open, reconRunning, training, sceneLoading, train.preset]);

  useEffect(() => {
    const msg = (reconMessage || train.message || '').trim();
    if (!msg || !open) return;
    setLogLines((prev) => {
      if (prev[prev.length - 1] === msg) return prev;
      const next = [...prev, msg];
      return next.length > OPS_LOG_CAP ? next.slice(-OPS_LOG_CAP) : next;
    });
  }, [reconMessage, train.message, open]);

  useEffect(() => {
    if (!open || busy || !wasBusyRef.current) return;
    if (train.status === 'error' || reconPhase === 'error' || (sceneError && sceneKind !== 'splat')) {
      setPhaseUi('error');
      addEvent('modal', 'recon-ops error', {
        error: train.error || sceneError || lastReconMessage,
      });
      wasBusyRef.current = false;
      return;
    }
    setPhaseUi('success');
    wasBusyRef.current = false;
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);

    const isTrainOp = opKindRef.current === 'train';
    // Hold train success until splat loads (or timeout) so operator sees pipeline end
    if (isTrainOp && sceneKind !== 'splat' && sceneLoading) {
      return;
    }
    const delay =
      isTrainOp && sceneKind !== 'splat' ? TRAIN_HOLD_DISMISS_MS : AUTO_DISMISS_MS;
    dismissTimerRef.current = setTimeout(() => {
      setOpen(false);
      setMinimized(false);
      setPhaseUi('work');
      startedAtRef.current = null;
      addEvent('modal', 'recon-ops auto-dismiss');
    }, delay);
  }, [
    busy,
    open,
    train.status,
    train.error,
    reconPhase,
    sceneError,
    lastReconMessage,
    sceneKind,
    sceneLoading,
  ]);

  // When splat appears after train success, dismiss shortly
  useEffect(() => {
    if (!open || phaseUi !== 'success' || opKindRef.current !== 'train') return;
    if (sceneKind !== 'splat') return;
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => {
      setOpen(false);
      setMinimized(false);
      setPhaseUi('work');
      startedAtRef.current = null;
      addEvent('modal', 'recon-ops auto-dismiss splat');
    }, AUTO_DISMISS_MS);
  }, [sceneKind, open, phaseUi]);

  useEffect(
    () => () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    },
    [],
  );

  const markDur = (id: string, status: OpsStepStatus) => {
    const now = Date.now();
    if (status === 'running' && stepStartRef.current[id] == null) stepStartRef.current[id] = now;
    if (
      (status === 'done' || status === 'error') &&
      stepStartRef.current[id] != null &&
      stepDurRef.current[id] == null
    ) {
      stepDurRef.current[id] = now - stepStartRef.current[id];
    }
    return stepDurRef.current[id];
  };

  const steps: OpsStep[] = useMemo(() => {
    void tick;
    const isTrain =
      opKindRef.current === 'train' ||
      training ||
      train.status === 'training' ||
      train.status === 'error';

    if (isTrain) {
      const err = train.status === 'error' || phaseUi === 'error';
      const doneAll = phaseUi === 'success';
      const trainingNow = training || train.status === 'training';
      const stepsDone = (train.steps ?? 0) > 0;
      const prepDone =
        err ||
        doneAll ||
        train.status === 'done' ||
        stepsDone ||
        /шаг|it\/s|loss=/i.test(train.message || '');
      const rows: OpsStep[] = [
        {
          id: 'train_prep',
          label: 'Подготовка (MSVC / данные)',
          status: prepDone ? 'done' : trainingNow ? 'running' : 'pending',
          detail:
            trainingNow && !prepDone
              ? train.message || 'MSVC / downscale / CUDA JIT…'
              : undefined,
        },
        {
          id: 'training',
          label: stepsDone
            ? `Обучение gsplat (${train.steps}/${train.max_steps ?? '?'} шагов)`
            : 'Обучение gsplat (JIT / шаги)',
          status: err
            ? 'error'
            : doneAll || (train.status === 'done' && !sceneLoading)
              ? 'done'
              : trainingNow && prepDone
                ? 'running'
                : 'pending',
          detail: err
            ? train.error || train.message || 'ошибка'
            : trainingNow && prepDone
              ? `${train.steps ?? 0}/${train.max_steps ?? 0} · loss ${train.loss != null ? train.loss.toFixed(4) : '—'} · PSNR ${train.psnr != null ? train.psnr.toFixed(1) : '—'} · VRAM ${(train.vram_used_gb ?? 0).toFixed(1)}/${(train.vram_total_gb ?? 0).toFixed(1)} GB`
              : trainingNow
                ? train.message || 'ожидание первого шага…'
                : undefined,
        },
        {
          id: 'write_ply',
          label: 'Запись model.ply',
          status: err
            ? 'pending'
            : doneAll || train.status === 'done'
              ? 'done'
              : trainingNow && (train.steps ?? 0) > 0 && train.max_steps
                ? (train.steps ?? 0) >= (train.max_steps ?? 1) * 0.95
                  ? 'running'
                  : 'pending'
                : 'pending',
        },
        {
          id: 'load_splat',
          label: 'Загрузка splat на сцену',
          status: err
            ? 'pending'
            : sceneLoading
              ? 'running'
              : doneAll || sceneKind === 'splat'
                ? 'done'
                : train.status === 'done'
                  ? 'running'
                  : 'pending',
        },
      ];
      return rows.map((r) => ({ ...r, durationMs: markDur(r.id, r.status) }));
    }

    const matcherLabel = matcherStepLabel(reconStage);
    const defs: { id: string; label: string }[] = [
      { id: 'extracting', label: 'Кадры из видео' },
      { id: 'plan', label: 'COLMAP plan' },
      { id: 'feature_extractor', label: 'feature_extractor' },
      { id: 'matcher', label: matcherLabel },
      { id: 'mapper', label: 'mapper' },
      { id: 'model_converter', label: 'model_converter' },
      { id: 'export_poses', label: 'Позы / sparse' },
      { id: 'load_scene', label: 'Загрузка сцены' },
    ];
    const idx = reconActiveIndex(reconPhase, reconStage, reconRunning, sceneLoading);
    const err = reconPhase === 'error' || (phaseUi === 'error' && opKindRef.current === 'recon');
    const errIdx =
      idx === -2
        ? Math.max(
            0,
            reconActiveIndex(
              reconPhase === 'error' ? 'colmap' : reconPhase,
              reconStage,
              true,
              false,
            ),
          )
        : idx;

    return defs.map((d, i) => {
      let status: OpsStepStatus = 'pending';
      if (phaseUi === 'success') status = 'done';
      else if (err) {
        const ei = errIdx >= 0 ? errIdx : 1;
        status = i < ei ? 'done' : i === ei ? 'error' : 'pending';
        if (sceneError && i === defs.length - 1) status = 'error';
      } else if (idx >= 100) status = 'done';
      else if (idx === 99) {
        // scene loading after recon
        status = i < defs.length - 1 ? 'done' : 'running';
      } else if (idx > i) status = 'done';
      else if (idx === i) status = 'running';
      else status = 'pending';
      return {
        ...d,
        status,
        detail:
          status === 'running'
            ? reconMessage
            : status === 'error'
              ? sceneError || lastReconMessage || reconMessage || undefined
              : undefined,
        durationMs: markDur(d.id, status),
      };
    });
  }, [
    tick,
    training,
    train,
    sceneLoading,
    reconRunning,
    reconPhase,
    reconStage,
    reconMessage,
    lastReconMessage,
    sceneError,
    phaseUi,
    sceneKind,
  ]);

  const progressPct = useMemo(() => {
    if (phaseUi === 'success' && (!training || sceneKind === 'splat')) return 100;
    if (training && train.max_steps) {
      return Math.min(99, Math.round(((train.steps ?? 0) / Math.max(1, train.max_steps)) * 100));
    }
    if (reconRunning) return Math.min(100, Math.round((reconProgress || 0) * 100));
    const done = steps.filter((s) => s.status === 'done').length;
    return steps.length ? Math.round((done / steps.length) * 100) : 0;
  }, [phaseUi, training, train, reconRunning, reconProgress, steps, sceneKind]);

  const elapsedSec = startedAtRef.current
    ? Math.max(0, Math.round((Date.now() - startedAtRef.current) / 1000))
    : 0;

  const current = steps.find((s) => s.status === 'running') || steps.find((s) => s.status === 'error');

  const title =
    opKindRef.current === 'train'
      ? phaseUi === 'success' && sceneKind !== 'splat'
        ? `Готово · model.ply — загрузка splat…`
        : `Обучение 3D${lastPresetRef.current ? ` · ${lastPresetRef.current}` : ''}`
      : opKindRef.current === 'load'
        ? 'Загрузка 3D-сцены'
        : 'Построение 3D (COLMAP)';

  const minimize = useCallback(() => {
    setMinimized(true);
    addEvent('modal', 'recon-ops minimize');
  }, []);

  const restore = useCallback(() => {
    setMinimized(false);
    addEvent('modal', 'recon-ops restore');
  }, []);

  const closeError = useCallback(() => {
    setOpen(false);
    setMinimized(false);
    setPhaseUi('work');
    startedAtRef.current = null;
    addEvent('modal', 'recon-ops close-error');
  }, []);

  const retry = useCallback(() => {
    setPhaseUi('work');
    setOpen(true);
    setMinimized(false);
    startedAtRef.current = Date.now();
    wasBusyRef.current = true;
    if (opKindRef.current === 'train') onRetryTrain?.(lastPresetRef.current);
    else onRetryRecon?.();
    addEvent('modal', 'recon-ops retry', { kind: opKindRef.current });
  }, [onRetryRecon, onRetryTrain]);

  // Prefer live SSE/status job_id over stale completed manifest
  const liveJobId =
    (reconRunning || phaseUi === 'work' || phaseUi === 'success' ? reconJobId : null) ||
    reconJobId ||
    (opKindRef.current === 'train' ? train.job_id : null) ||
    manifest?.job_id ||
    null;

  return {
    visible: open,
    minimized,
    finishing: phaseUi === 'success',
    isError: phaseUi === 'error',
    title,
    jobId: liveJobId as string | null,
    steps,
    current,
    progressPct,
    elapsedSec,
    logLines,
    errorMessage: train.error || sceneError || (phaseUi === 'error' ? lastReconMessage || reconMessage : null),
    minimize,
    restore,
    closeError,
    retry,
    logCap: OPS_LOG_CAP,
  };
}
