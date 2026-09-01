import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Brain, Loader2, RefreshCw, Zap } from 'lucide-react';
import { resolveVisionImage, type VisionImageSource } from '../../lib/aiVision';
import { useMuraveiStore } from '../../store/useMuraveiStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { RulesPanel } from './RulesPanel';

interface OllamaModel {
  name: string;
}

interface HistoryItem {
  id: string;
  ts: number;
  model: string;
  prompt: string;
  ok: boolean;
  latencyMs: number;
  analysis?: string;
  error?: string;
  hadImage?: boolean;
}

const AI_UNAVAILABLE =
  'Локальная ИИ-модель недоступна. Запустите Ollama на этом компьютере.';
const HISTORY_KEY = 'muravei-ai-analysis-history';
const SMOKE_PROMPT = 'Ответь одним словом: ok';

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('muravei-token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistoryItem[];
    return Array.isArray(parsed) ? parsed.slice(0, 10) : [];
  } catch {
    return [];
  }
}

function saveHistory(items: HistoryItem[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(items.slice(0, 10)));
}

const SOURCE_HINT: Record<VisionImageSource, string> = {
  detection: 'кроп выбранной детекции',
  'playhead-detection': 'кроп детекции у playhead',
  preview: 'кадр из вьюера (preview)',
  'video-frame': 'кадр видео по времени playhead',
  none: 'не выбран — выберите детекцию или перемотайте playhead',
};

export const AiAnalysisPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const activeDetectionId = useMuraveiStore((s) => s.activeDetectionId);
  const detections = useMuraveiStore((s) => s.detections);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const sourcePath = useViewerStore((s) => s.viewers[focusedViewerId]?.sourcePath);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const previewFrame = useTimelineStore((s) => s.previewFrame);

  const [models, setModels] = useState<OllamaModel[]>([]);
  const [model, setModel] = useState('');
  const [available, setAvailable] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [prompt, setPrompt] = useState('Определи тип маскировки и уверенность.');
  const [busy, setBusy] = useState(false);
  const [smokeBusy, setSmokeBusy] = useState(false);
  const [smokeMs, setSmokeMs] = useState<number | null>(null);
  const [smokeOk, setSmokeOk] = useState<boolean | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>(() => loadHistory());
  const [cropLabel, setCropLabel] = useState('…');
  const [cropSource, setCropSource] = useState<VisionImageSource>('none');

  const refreshModels = useCallback(async () => {
    if (!isAuthenticated) {
      setAvailable(false);
      setModels([]);
      setStatusMsg('Войдите, чтобы загрузить модели Ollama');
      return;
    }
    try {
      const res = await fetch('/api/ai/models', { headers: authHeaders() });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setAvailable(false);
        setModels([]);
        setStatusMsg(typeof data.detail === 'string' ? data.detail : AI_UNAVAILABLE);
        return;
      }
      const list = Array.isArray(data.models) ? (data.models as OllamaModel[]) : [];
      setModels(list);
      setAvailable(Boolean(data.available) && list.length > 0);
      setModel((prev) => prev || list[0]?.name || '');
      setStatusMsg(
        data.available
          ? list.length
            ? null
            : 'Ollama доступна, но список моделей пуст'
          : data.message || AI_UNAVAILABLE,
      );
    } catch {
      setAvailable(false);
      setModels([]);
      setStatusMsg(AI_UNAVAILABLE);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    void refreshModels();
    const t = window.setInterval(() => void refreshModels(), 20000);
    return () => window.clearInterval(t);
  }, [refreshModels]);

  useEffect(() => {
    let cancelled = false;
    void resolveVisionImage({
      activeDetectionId,
      detections,
      sourcePath,
      playheadSec: playheadPosition,
      previewFrame,
    }).then((res) => {
      if (cancelled) return;
      setCropLabel(res.label);
      setCropSource(res.source);
    });
    return () => {
      cancelled = true;
    };
  }, [activeDetectionId, detections, sourcePath, playheadPosition, previewFrame]);

  const pushHistory = (item: HistoryItem) => {
    setHistory((prev) => {
      const next = [item, ...prev].slice(0, 10);
      saveHistory(next);
      return next;
    });
  };

  const runSmoke = async () => {
    setSmokeBusy(true);
    setSmokeOk(null);
    setSmokeMs(null);
    const t0 = performance.now();
    try {
      const res = await fetch('/api/ai/analyze', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ prompt: SMOKE_PROMPT, model: model || undefined }),
      });
      const ms = Math.round(performance.now() - t0);
      setSmokeMs(ms);
      const data = await res.json().catch(() => ({}));
      const ok = res.ok && typeof data.analysis === 'string';
      setSmokeOk(ok);
      pushHistory({
        id: `smoke-${Date.now()}`,
        ts: Date.now(),
        model: model || data.model || 'default',
        prompt: SMOKE_PROMPT,
        ok,
        latencyMs: ms,
        analysis: ok ? String(data.analysis).slice(0, 200) : undefined,
        error: ok ? undefined : AI_UNAVAILABLE,
      });
      if (!ok) setStatusMsg(AI_UNAVAILABLE);
    } catch {
      setSmokeOk(false);
      setSmokeMs(Math.round(performance.now() - t0));
      setStatusMsg(AI_UNAVAILABLE);
    } finally {
      setSmokeBusy(false);
    }
  };

  const runAnalyze = async () => {
    setBusy(true);
    setStatusMsg(null);
    const t0 = performance.now();
    const detection = detections.find((d) => d.id === activeDetectionId);
    try {
      const vision = await resolveVisionImage({
        activeDetectionId,
        detections,
        sourcePath,
        playheadSec: playheadPosition,
        previewFrame,
      });
      setCropLabel(vision.label);
      setCropSource(vision.source);

      if (!vision.base64) {
        const err =
          'Нет изображения для анализа. Выберите детекцию в Inspector или откройте видео во вьюере.';
        setStatusMsg(err);
        pushHistory({
          id: `an-${Date.now()}`,
          ts: Date.now(),
          model: model || 'default',
          prompt: prompt.trim() || '(default)',
          ok: false,
          latencyMs: Math.round(performance.now() - t0),
          error: err,
          hadImage: false,
        });
        return;
      }

      const res = await fetch('/api/ai/analyze', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          prompt: prompt.trim() || undefined,
          model: model || undefined,
          detection_id: detection?.id,
          image_base64: vision.base64,
        }),
      });
      const ms = Math.round(performance.now() - t0);
      const data = await res.json().catch(() => ({}));
      const ok = res.ok && typeof data.analysis === 'string' && data.analysis.trim();
      const hadImage = Boolean(data.had_image ?? vision.base64);
      pushHistory({
        id: `an-${Date.now()}`,
        ts: Date.now(),
        model: model || data.model || 'default',
        prompt: prompt.trim() || '(default)',
        ok: Boolean(ok),
        latencyMs: ms,
        analysis: ok ? String(data.analysis).trim() : undefined,
        error: ok ? undefined : (typeof data.detail === 'string' ? data.detail : AI_UNAVAILABLE),
        hadImage,
      });
      if (!ok) {
        setStatusMsg(typeof data.detail === 'string' ? data.detail : AI_UNAVAILABLE);
      } else if (!hadImage) {
        setStatusMsg('Модель ответила без просмотра кадра — проверьте vision-модель (qwen2.5-vl).');
      }
    } catch {
      pushHistory({
        id: `an-${Date.now()}`,
        ts: Date.now(),
        model: model || 'default',
        prompt: prompt.trim() || '(default)',
        ok: false,
        latencyMs: Math.round(performance.now() - t0),
        error: AI_UNAVAILABLE,
        hadImage: false,
      });
      setStatusMsg(AI_UNAVAILABLE);
    } finally {
      setBusy(false);
    }
  };

  const cropReady = cropSource !== 'none';

  return (
    <div className="h-full flex flex-col bg-[var(--dv-panel)] text-[var(--dv-text)] text-xs overflow-hidden">
      <div className="px-3 py-2 border-b border-[var(--dv-border)] flex items-center gap-2 flex-shrink-0">
        <Brain size={14} className="text-[var(--dv-accent)]" />
        <span className="font-semibold text-[11px] tracking-wide">AI Analysis</span>
        <button
          type="button"
          className="ml-auto p-1 rounded-sm hover:bg-[#333] text-[var(--dv-text-muted)]"
          title="Обновить модели"
          onClick={() => void refreshModels()}
        >
          <RefreshCw size={12} />
        </button>
      </div>

      <div className="flex-1 overflow-auto p-3 space-y-3">
        <RulesPanel />
        {!isAuthenticated && (
          <div className="flex gap-2 items-start rounded-sm border border-amber-700/60 bg-amber-950/40 px-2 py-1.5 text-amber-200">
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            <span>Войдите в систему — иначе кроп и API недоступны.</span>
          </div>
        )}

        {!available && isAuthenticated && (
          <div className="flex gap-2 items-start rounded-sm border border-amber-700/60 bg-amber-950/40 px-2 py-1.5 text-amber-200">
            <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" />
            <span>{statusMsg || AI_UNAVAILABLE}</span>
          </div>
        )}

        {statusMsg && available && (
          <div className="text-[10px] text-amber-300">{statusMsg}</div>
        )}

        <label className="block space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Модель Ollama
          </span>
          <select
            className="w-full bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1.5 rounded-sm"
            value={model}
            disabled={!models.length}
            onChange={(e) => setModel(e.target.value)}
          >
            {!models.length && <option value="">Нет моделей</option>}
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}
              </option>
            ))}
          </select>
        </label>

        <div className="flex gap-2">
          <button
            type="button"
            disabled={!isAuthenticated || smokeBusy}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-sm bg-[#2e2e2e] hover:bg-[#3a3a3a] disabled:opacity-40"
            onClick={() => void runSmoke()}
          >
            {smokeBusy ? <Loader2 size={12} className="animate-spin" /> : <Zap size={12} />}
            Smoke-тест Ollama
          </button>
        </div>
        {smokeOk !== null && (
          <div className={`text-[10px] ${smokeOk ? 'text-emerald-400' : 'text-red-400'}`}>
            {smokeOk ? 'OK' : 'FAIL'}
            {smokeMs != null ? ` · ${smokeMs} ms` : ''}
          </div>
        )}

        <label className="block space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            Промпт
          </span>
          <textarea
            className="w-full h-20 resize-none bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-2 py-1.5 rounded-sm"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="например: определи тип маскировки"
          />
        </label>

        <div
          className={`text-[10px] ${cropReady ? 'text-emerald-400' : 'text-[var(--dv-text-muted)]'}`}
        >
          Кроп: {cropLabel}
          <span className="text-[var(--dv-text-muted)]"> · {SOURCE_HINT[cropSource]}</span>
        </div>

        <button
          type="button"
          disabled={!isAuthenticated || busy || !cropReady}
          className="w-full py-2 rounded-sm bg-[var(--dv-accent)] text-black font-medium disabled:opacity-40 flex items-center justify-center gap-1.5"
          onClick={() => void runAnalyze()}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Brain size={13} />}
          Анализ ИИ
        </button>

        <div className="space-y-1.5">
          <div className="text-[10px] uppercase tracking-wider text-[var(--dv-text-muted)]">
            История (последние 10)
          </div>
          {history.length === 0 && (
            <div className="text-[var(--dv-text-muted)]">Пока пусто</div>
          )}
          {history.map((h) => (
            <div
              key={h.id}
              className="border border-[var(--dv-border)] rounded-sm p-2 space-y-1 bg-[var(--dv-bg-deep)]"
            >
              <div className="flex justify-between gap-2 text-[10px] text-[var(--dv-text-muted)]">
                <span>{new Date(h.ts).toLocaleTimeString()}</span>
                <span>
                  {h.model} · {h.latencyMs} ms ·{' '}
                  <span className={h.ok ? 'text-emerald-400' : 'text-red-400'}>
                    {h.ok ? 'ok' : 'err'}
                  </span>
                  {h.hadImage === false ? ' · no img' : h.hadImage ? ' · img' : ''}
                </span>
              </div>
              <div className="truncate text-[var(--dv-text-muted)]" title={h.prompt}>
                {h.prompt}
              </div>
              {h.analysis && (
                <div className="whitespace-pre-wrap text-[11px] leading-snug max-h-24 overflow-auto">
                  {h.analysis}
                </div>
              )}
              {h.error && <div className="text-red-400 text-[10px]">{h.error}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AiAnalysisPanel;
