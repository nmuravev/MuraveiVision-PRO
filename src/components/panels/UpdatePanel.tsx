import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Check, Download, Film, LifeBuoy, Package, Square, X, Zap } from 'lucide-react';
import { downloadAuthorized } from '../../lib/download';
import { readSse } from '../../lib/readSse';
import { batchScanProgressPct, useBatchScanStore } from '../../store/useBatchScanStore';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { useViewerStore } from '../../store/useViewerStore';

type TrainCheckpoint = {
  name: string;
  size_mb: number;
  mtime: number;
  resumable: boolean;
  metrics?: { epoch?: number; map50?: number } | null;
};

function vramRisk(imgsz: number, batch: number, vramMb: number): 'ok' | 'warn' | 'danger' {
  if (vramMb >= 12000) return 'ok';
  if (imgsz <= 640 && batch <= 4) return 'ok';
  if (imgsz <= 640 && batch <= 8) return 'warn';
  if (imgsz <= 800 && batch <= 4) return 'warn';
  return 'danger';
}

type ActiveLearningSample = {
  id: string;
  detection_id: string;
  class_name: string;
  proposed_class?: string | null;
  confidence: number;
  time_sec: number;
};
import { RulesPanel } from './RulesPanel';

export const UpdatePanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const userRole = useMuraveiStore((s) => s.userRole);
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);
  const [info, setInfo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [trainStatus, setTrainStatus] = useState<string>('idle');
  const [trainMsg, setTrainMsg] = useState('');
  const [trainEpoch, setTrainEpoch] = useState(0);
  const [trainEpochs, setTrainEpochs] = useState(10);
  const [trainLog, setTrainLog] = useState<string[]>([]);
  const [trainImgsz, setTrainImgsz] = useState(640);
  const [trainBatch, setTrainBatch] = useState(4);
  const [checkpoints, setCheckpoints] = useState<TrainCheckpoint[]>([]);
  const [canResume, setCanResume] = useState(false);
  const [vramMb, setVramMb] = useState(8192);
  const [reviewSamples, setReviewSamples] = useState<ActiveLearningSample[]>([]);
  const [reviewBusy, setReviewBusy] = useState(false);
  const scanStatus = useBatchScanStore((s) => s.status);
  const scanMsg = useBatchScanStore((s) => s.message);
  const scanProcessed = useBatchScanStore((s) => s.processed);
  const scanSampleTotal = useBatchScanStore((s) => s.sampleTotal);
  const scanFound = useBatchScanStore((s) => s.found);
  const startBatchScan = useBatchScanStore((s) => s.startScan);
  const stopBatchScan = useBatchScanStore((s) => s.stopScan);

  const fileLabel = sourcePath ? sourcePath.replace(/^.*[/\\]/, '') : null;
  const isVideo =
    Boolean(sourcePath) && /\.(mp4|webm|mov|avi|mkv)$/i.test(sourcePath || '');

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    setError(null);
    setInfo(null);
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка');
    } finally {
      setBusy(null);
    }
  };

  const appendLog = (line: string) => {
    setTrainLog((prev) => [...prev.slice(-40), line]);
  };

  const loadCheckpoints = useCallback(async () => {
    if (!isAuthenticated) {
      setCheckpoints([]);
      setCanResume(false);
      return;
    }
    const res = await fetch('/api/train/checkpoints', { headers: authHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as {
      checkpoints?: TrainCheckpoint[];
      can_resume?: boolean;
      vram_mb?: number;
    };
    setCheckpoints(Array.isArray(data.checkpoints) ? data.checkpoints : []);
    setCanResume(Boolean(data.can_resume));
    if (typeof data.vram_mb === 'number') setVramMb(data.vram_mb);
  }, [isAuthenticated]);

  const startTrain = async (opts?: { resumeFrom?: string }) => {
    setError(null);
    setInfo(null);
    setTrainLog([]);
    const res = await fetch('/api/train/start', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        epochs: 10,
        imgsz: trainImgsz,
        batch: trainBatch,
        resume_from: opts?.resumeFrom ?? null,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Train start failed');
    }
    setTrainStatus(data.status || 'running');
    setTrainMsg(data.message || 'Starting…');
    await readSse('/api/train/stream', (ev) => {
      if (typeof ev.status === 'string') setTrainStatus(ev.status);
      if (typeof ev.message === 'string') {
        setTrainMsg(ev.message);
        appendLog(ev.message);
      }
      if (typeof ev.epoch === 'number') setTrainEpoch(ev.epoch);
      if (typeof ev.epochs === 'number') setTrainEpochs(ev.epochs);
      if (typeof ev.box_loss === 'number' || typeof ev.cls_loss === 'number') {
        appendLog(
          `loss box=${ev.box_loss ?? '—'} cls=${ev.cls_loss ?? '—'} mAP50=${ev.map50 ?? '—'}`,
        );
      }
      if (ev.status === 'done') {
        setInfo('Дообучение завершено. Модель обновлена.');
        void loadCheckpoints();
      }
      if (ev.status === 'error') setError(String(ev.error || ev.message || 'Train error'));
    });
  };

  const stopTrain = async () => {
    await fetch('/api/train/stop', { method: 'POST', headers: authHeaders() });
    setTrainMsg('Stop requested…');
  };

  const startScan = async () => {
    if (!sourcePath || !isVideo) {
      throw new Error('Откройте MP4 во Viewer');
    }
    await startBatchScan(sourcePath, hydrateDetections);
  };

  const stopScan = async () => {
    await stopBatchScan();
  };

  const loadReviewQueue = useCallback(async () => {
    if (!isAuthenticated) {
      setReviewSamples([]);
      return;
    }
    const params = new URLSearchParams({ status: 'pending' });
    if (sourcePath) params.set('source_video', sourcePath);
    const res = await fetch(`/api/active-learning?${params}`, { headers: authHeaders() });
    if (!res.ok) return;
    const data = (await res.json()) as { samples?: ActiveLearningSample[] };
    setReviewSamples(Array.isArray(data.samples) ? data.samples : []);
  }, [isAuthenticated, sourcePath]);

  useEffect(() => {
    void loadReviewQueue();
  }, [loadReviewQueue]);

  useEffect(() => {
    void loadCheckpoints();
  }, [loadCheckpoints]);

  const collectReviewQueue = async () => {
    setReviewBusy(true);
    try {
      const res = await fetch('/api/active-learning/collect', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ source_video: sourcePath || null, max_confidence: 0.5 }),
      });
      if (!res.ok) throw new Error('Не удалось собрать очередь проверки');
      await loadReviewQueue();
    } finally {
      setReviewBusy(false);
    }
  };

  const decideReview = async (
    sample: ActiveLearningSample,
    status: 'accepted' | 'rejected',
  ) => {
    setReviewBusy(true);
    try {
      const res = await fetch(`/api/active-learning/${encodeURIComponent(sample.id)}/decision`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          status,
          class_name: sample.proposed_class || sample.class_name,
        }),
      });
      if (!res.ok) throw new Error('Не удалось сохранить решение');
      if (sourcePath) await hydrateDetections(sourcePath);
      await loadReviewQueue();
    } finally {
      setReviewBusy(false);
    }
  };

  const risk = useMemo(
    () => vramRisk(trainImgsz, trainBatch, vramMb),
    [trainImgsz, trainBatch, vramMb],
  );

  const pct =
    trainEpochs > 0 && trainEpoch > 0
      ? Math.min(100, Math.round((trainEpoch / trainEpochs) * 100))
      : trainStatus === 'done'
        ? 100
        : trainStatus === 'running'
          ? 5
          : 0;

  const scanPct = batchScanProgressPct({
    status: scanStatus,
    processed: scanProcessed,
    sampleTotal: scanSampleTotal,
  });

  return (
    <div className="h-full overflow-auto p-4 space-y-4 text-[12px]">
      <div>
        <div className="text-[11px] uppercase tracking-wider text-[var(--dv-text-muted)] font-semibold">
          Обновление
        </div>
        <p className="text-[11px] text-[var(--dv-text-muted)] mt-1">
          Оператор: пакетный анализ архива, быстрое дообучение, выгрузка датасета и диагностика.
          {userRole ? ` Роль: ${userRole}.` : ''}
        </p>
      </div>

      {!isAuthenticated && (
        <div className="text-[11px] text-[var(--dv-accent)]">Войдите PIN оператора.</div>
      )}

      <RulesPanel />

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="flex items-center gap-2 text-[var(--dv-text)]">
          <Film size={14} className="text-sky-400" />
          <span className="font-semibold">Пакетный анализ видео</span>
        </div>
        <p className="text-[11px] text-[var(--dv-text-muted)]">
          Фоновый прогон YOLO по архивному ролику (~1 кадр/сек). Детекции пишутся в БД
          (origin=batch_scan) и появляются маркерами на таймлайне. Realtime Viewer не
          блокируется.
        </p>
        <div className="text-[10px] text-[var(--dv-text-muted)] font-mono truncate">
          {isVideo ? `Источник: ${fileLabel}` : 'Откройте MP4 во Viewer'}
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            disabled={
              !isAuthenticated ||
              !isVideo ||
              scanStatus === 'running' ||
              trainStatus === 'running' ||
              busy !== null
            }
            className="px-3 py-1.5 bg-sky-600 text-white rounded-sm disabled:opacity-40 font-medium"
            onClick={() => void run('scan', startScan)}
          >
            {scanStatus === 'running' ? 'Сканирование…' : 'Начать скан'}
          </button>
          <button
            type="button"
            disabled={scanStatus !== 'running'}
            className="px-3 py-1.5 bg-[#333] rounded-sm disabled:opacity-40 inline-flex items-center gap-1"
            onClick={() => void stopScan()}
          >
            <Square size={12} />
            Остановить
          </button>
        </div>
        <div className="h-2 bg-[#1a1a1a] border border-[var(--dv-border)] rounded-sm overflow-hidden">
          <div
            className="h-full bg-sky-500 transition-all"
            style={{ width: `${scanPct}%` }}
          />
        </div>
        <div className="text-[10px] text-[var(--dv-text-muted)] font-mono">
          {scanStatus}
          {scanProcessed > 0 || scanFound > 0
            ? ` · кадров ${scanProcessed}${scanSampleTotal ? ` / ${scanSampleTotal}` : ''} · целей ${scanFound}`
            : ''}
          {scanMsg ? ` · ${scanMsg}` : ''}
        </div>
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="font-semibold">Active Learning — проверка</div>
          <button
            type="button"
            disabled={!isAuthenticated || reviewBusy}
            className="px-2 py-1 bg-[#333] rounded-sm disabled:opacity-40"
            onClick={() => void collectReviewQueue()}
          >
            Собрать ≤ 0.50
          </button>
        </div>
        <p className="text-[10px] text-[var(--dv-text-muted)]">
          Подтверждённые примеры остаются в датасете, отклонённые становятся
          soft-deleted false positives.
        </p>
        {reviewSamples.length === 0 ? (
          <div className="text-[10px] text-[var(--dv-text-muted)]">Очередь пуста</div>
        ) : (
          <div className="max-h-40 overflow-auto space-y-1">
            {reviewSamples.map((sample) => (
              <div
                key={sample.id}
                className="flex items-center gap-2 border border-[var(--dv-border)] px-2 py-1 text-[10px]"
              >
                <span className="flex-1 truncate">
                  {sample.proposed_class || sample.class_name} ·{' '}
                  {sample.confidence.toFixed(2)} · {sample.time_sec.toFixed(1)}s
                </span>
                <button
                  type="button"
                  title="Подтвердить"
                  disabled={reviewBusy}
                  className="text-emerald-400 disabled:opacity-40"
                  onClick={() => void decideReview(sample, 'accepted')}
                >
                  <Check size={13} />
                </button>
                <button
                  type="button"
                  title="False positive"
                  disabled={reviewBusy}
                  className="text-red-400 disabled:opacity-40"
                  onClick={() => void decideReview(sample, 'rejected')}
                >
                  <X size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="flex items-center gap-2 text-[var(--dv-text)]">
          <Zap size={14} className="text-[var(--dv-accent)]" />
          <span className="font-semibold">Быстрое улучшение</span>
        </div>
        <p className="text-[11px] text-[var(--dv-text-muted)]">
          Detect-only YOLO26n/ft. По умолчанию imgsz=640, batch=4 (безопасно для 8 ГБ VRAM).
          Без YOLOE/seg. Resume подхватывает last.pt прерванного прогона.
        </p>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <label className="space-y-0.5">
            <span className="text-[var(--dv-text-muted)]">imgsz ({trainImgsz})</span>
            <input
              type="range"
              min={320}
              max={1024}
              step={32}
              value={trainImgsz}
              disabled={trainStatus === 'running'}
              onChange={(e) => setTrainImgsz(Number(e.target.value))}
              className="w-full"
            />
          </label>
          <label className="space-y-0.5">
            <span className="text-[var(--dv-text-muted)]">batch ({trainBatch})</span>
            <input
              type="range"
              min={1}
              max={8}
              step={1}
              value={trainBatch}
              disabled={trainStatus === 'running'}
              onChange={(e) => setTrainBatch(Number(e.target.value))}
              className="w-full"
            />
          </label>
        </div>
        {risk !== 'ok' && (
          <div
            className={`text-[10px] flex items-center gap-1 ${
              risk === 'danger' ? 'text-red-400' : 'text-amber-400'
            }`}
          >
            <AlertTriangle size={12} />
            {risk === 'danger'
              ? `Риск OOM на ${vramMb} МБ VRAM. Опустите imgsz до 640 и batch до 4.`
              : `Повышенная нагрузка на ${vramMb} МБ VRAM. При обрыве — «Продолжить обучение».`}
          </div>
        )}
        <div className="border border-[var(--dv-border)] p-2 space-y-1">
          <div className="text-[10px] uppercase tracking-wide text-[var(--dv-text-muted)]">
            Точки восстановления
          </div>
          {checkpoints.length === 0 ? (
            <div className="text-[10px] text-[var(--dv-text-muted)]">
              Нет last.pt / best.pt. Сначала запустите быстрое улучшение.
            </div>
          ) : (
            <ul className="text-[10px] font-mono space-y-0.5 max-h-20 overflow-auto">
              {checkpoints.slice(0, 8).map((ck) => (
                <li key={`${ck.name}-${ck.mtime}`}>
                  {ck.name}
                  {ck.resumable ? ' · resume' : ''}
                  {ck.metrics?.map50 != null ? ` · mAP50 ${ck.metrics.map50}` : ''}
                  {` · ${ck.size_mb} МБ`}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            type="button"
            disabled={
              !isAuthenticated ||
              trainStatus === 'running' ||
              scanStatus === 'running' ||
              busy !== null
            }
            className="px-3 py-1.5 bg-[var(--dv-accent)] text-black rounded-sm disabled:opacity-40 font-medium"
            onClick={() => void run('train', () => startTrain())}
          >
            {trainStatus === 'running' ? 'Обучение…' : 'Быстрое улучшение'}
          </button>
          <button
            type="button"
            disabled={
              !isAuthenticated ||
              !canResume ||
              trainStatus === 'running' ||
              scanStatus === 'running' ||
              busy !== null
            }
            className="px-3 py-1.5 bg-sky-700 text-white rounded-sm disabled:opacity-40 font-medium"
            onClick={() => void run('train', () => startTrain({ resumeFrom: 'last.pt' }))}
          >
            Продолжить обучение
          </button>
          <button
            type="button"
            disabled={trainStatus !== 'running'}
            className="px-3 py-1.5 bg-[#333] rounded-sm disabled:opacity-40 inline-flex items-center gap-1"
            onClick={() => void stopTrain()}
          >
            <Square size={12} />
            Стоп
          </button>
        </div>
        <div className="h-2 bg-[#1a1a1a] border border-[var(--dv-border)] rounded-sm overflow-hidden">
          <div
            className="h-full bg-[var(--dv-accent)] transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="text-[10px] text-[var(--dv-text-muted)] font-mono">
          {trainStatus} · epoch {trainEpoch}/{trainEpochs} · {trainMsg}
        </div>
        {trainLog.length > 0 && (
          <pre className="max-h-28 overflow-auto text-[10px] bg-black/40 p-2 border border-[var(--dv-border)]">
            {trainLog.join('\n')}
          </pre>
        )}
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="flex items-center gap-2">
          <Package size={14} className="text-purple-400" />
          <span className="font-semibold">Собрать данные для инженера</span>
        </div>
        <button
          type="button"
          disabled={!isAuthenticated || busy !== null}
          className="px-3 py-1.5 bg-[#333] hover:bg-[#3a3a3a] rounded-sm disabled:opacity-40 inline-flex items-center gap-1"
          onClick={() =>
            void run('dataset', async () => {
              await downloadAuthorized('/api/export/dataset-zip', {
                method: 'POST',
                filename: `muravei-dataset-${Date.now()}.zip`,
              });
              setInfo('Архив датасета скачан');
            })
          }
        >
          <Download size={12} />
          {busy === 'dataset' ? 'Упаковка…' : 'Собрать данные для инженера'}
        </button>
      </div>

      <div className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] p-3 space-y-2">
        <div className="flex items-center gap-2">
          <LifeBuoy size={14} className="text-orange-400" />
          <span className="font-semibold">Техподдержка</span>
        </div>
        <button
          type="button"
          disabled={!isAuthenticated || busy !== null}
          className="px-3 py-1.5 bg-[#333] hover:bg-[#3a3a3a] rounded-sm disabled:opacity-40 inline-flex items-center gap-1"
          onClick={() =>
            void run('support', async () => {
              await downloadAuthorized('/api/support/diagnostic-zip', {
                method: 'POST',
                filename: `muravei-diagnostic-${Date.now()}.zip`,
              });
              setInfo('Диагностический ZIP скачан');
            })
          }
        >
          <Download size={12} />
          {busy === 'support' ? 'Сбор…' : 'Техподдержка'}
        </button>
      </div>

      {info && (
        <div className="border border-[var(--dv-border)] px-3 py-2 text-[11px] text-[var(--dv-accent)]">{info}</div>
      )}
      {error && (
        <div className="border border-red-900 px-3 py-2 text-[11px] text-red-400 flex items-center gap-1">
          <AlertTriangle size={12} />
          {error}
        </div>
      )}
    </div>
  );
};

export default UpdatePanel;
