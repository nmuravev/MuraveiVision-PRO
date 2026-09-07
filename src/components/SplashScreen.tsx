import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Loader2, RefreshCw, XCircle } from 'lucide-react';
import { logger } from '../services/logger';

export type SplashStepStatus = 'pending' | 'running' | 'ok' | 'error';

interface SplashStep {
  id: string;
  label: string;
  status: SplashStepStatus;
  detail?: string;
}

const SPLASH_DONE_KEY = 'muravei-splash-done-v1';

const INITIAL: SplashStep[] = [
  { id: 'db', label: 'Инициализация базы данных…', status: 'pending' },
  { id: 'model', label: 'Загрузка модели YOLO26…', status: 'pending' },
  { id: 'api', label: 'Подключение к API…', status: 'pending' },
  { id: 'ollama', label: 'Проверка Ollama…', status: 'pending' },
  { id: 'ready', label: 'Готово к работе', status: 'pending' },
];

interface SplashScreenProps {
  onDone: () => void;
  /** Force run even if already completed once in this browser. */
  force?: boolean;
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem('muravei-token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function shouldShowSplash(force?: boolean): boolean {
  if (force) return true;
  try {
    return localStorage.getItem(SPLASH_DONE_KEY) !== '1';
  } catch {
    return true;
  }
}

export const SplashScreen: React.FC<SplashScreenProps> = ({ onDone, force }) => {
  const [steps, setSteps] = useState<SplashStep[]>(INITIAL);
  const [fatal, setFatal] = useState<string | null>(null);
  const [fading, setFading] = useState(false);
  const [runId, setRunId] = useState(0);

  const patch = (id: string, patchStep: Partial<SplashStep>) => {
    setSteps((prev) => prev.map((s) => (s.id === id ? { ...s, ...patchStep } : s)));
  };

  const finishOk = useCallback(() => {
    try {
      localStorage.setItem(SPLASH_DONE_KEY, '1');
    } catch {
      /* ignore */
    }
    setFading(true);
    window.setTimeout(() => onDone(), 500);
  }, [onDone]);

  useEffect(() => {
    if (!force && !shouldShowSplash()) {
      onDone();
      return;
    }

    let cancelled = false;

    const run = async () => {
      setFatal(null);
      setSteps(INITIAL.map((s) => ({ ...s, status: 'pending', detail: undefined })));

      // 1) DB via health (init_db runs on lifespan)
      patch('db', { status: 'running' });
      logger.info('splash', 'Проверка БД / API…');
      try {
        const res = await fetch('/api/health');
        const data = await res.json().catch(() => ({}));
        if (cancelled) return;
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        patch('db', {
          status: data.db === false ? 'error' : 'ok',
          detail: data.db === false ? 'muravei.db отсутствует' : 'muravei.db OK',
        });
        if (data.db === false) {
          setFatal('База данных не инициализирована');
          return;
        }
        patch('api', { status: 'ok', detail: `v${data.version || '1.0.0'}` });

        patch('model', { status: 'running' });
        const ym = String(data.yolo_mode || '');
        if (ym === 'ready') {
          patch('model', {
            status: 'ok',
            detail: data.yolo_model || 'ready',
          });
        } else if (ym === 'offline' || ym === 'error') {
          patch('model', {
            status: 'ok',
            detail: `режим ${ym} (можно импортировать веса)`,
          });
          logger.warn('splash', `YOLO mode=${ym}`);
        } else {
          patch('model', { status: 'ok', detail: ym || 'проверка позже' });
        }
      } catch (err) {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : 'Ошибка API';
        patch('db', { status: 'error', detail: msg });
        patch('api', { status: 'error', detail: msg });
        patch('model', { status: 'error', detail: msg });
        setFatal(`Не удалось подключиться к API: ${msg}`);
        logger.error('splash', msg);
        return;
      }

      // Ollama (optional — warn only)
      patch('ollama', { status: 'running' });
      try {
        const res = await fetch('/api/ai/models', { headers: authHeaders() });
        if (cancelled) return;
        if (res.status === 401 || res.status === 403) {
          patch('ollama', {
            status: 'ok',
            detail: 'Войдите PIN — затем проверка моделей',
          });
        } else if (res.ok) {
          const data = await res.json();
          const n = Array.isArray(data.models) ? data.models.length : 0;
          if (data.available && n > 0) {
            patch('ollama', { status: 'ok', detail: `${n} моделей` });
          } else {
            patch('ollama', {
              status: 'ok',
              detail: 'не подключена (опционально)',
            });
          }
        } else {
          patch('ollama', { status: 'ok', detail: 'Пропуск (не критично)' });
        }
      } catch {
        if (cancelled) return;
        patch('ollama', { status: 'ok', detail: 'Пропуск (не критично)' });
      }

      if (cancelled) return;
      patch('ready', { status: 'ok', detail: 'Система готова' });
      logger.info('splash', 'Инициализация завершена');
      finishOk();
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [force, finishOk, onDone, runId]);

  const doneCount = steps.filter((s) => s.status === 'ok' || s.status === 'error').length;
  const pct = Math.round((doneCount / steps.length) * 100);

  return (
    <div
      className={`fixed inset-0 z-[9999] flex items-center justify-center bg-[#0a0a0a] transition-opacity duration-500 ${
        fading ? 'opacity-0 pointer-events-none' : 'opacity-100'
      }`}
    >
      <div className="w-full max-w-md px-6 space-y-6">
        <div className="text-center space-y-1">
          <div className="inline-flex w-12 h-12 items-center justify-center rounded-sm bg-[var(--dv-accent-hot,#e87d0d)] text-white font-bold text-xl mb-2">
            M
          </div>
          <h1 className="text-xl font-semibold text-[#e8e8e8] tracking-wide">
            MuraveiVision PRO
          </h1>
          <p className="text-xs text-[#888]">версия v3.0 · автономный комплекс</p>
        </div>

        <div className="h-1.5 rounded-full bg-[#222] overflow-hidden">
          <div
            className="h-full bg-[var(--dv-accent,#e87d0d)] transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>

        <ul className="space-y-2.5">
          {steps.map((s) => (
            <li key={s.id} className="flex items-start gap-2.5 text-sm text-[#ccc]">
              <span className="mt-0.5 flex-shrink-0">
                {s.status === 'running' && (
                  <Loader2 size={16} className="animate-spin text-amber-400" />
                )}
                {s.status === 'ok' && <CheckCircle2 size={16} className="text-emerald-400" />}
                {s.status === 'error' && <XCircle size={16} className="text-red-400" />}
                {s.status === 'pending' && (
                  <span className="inline-block w-4 h-4 rounded-full border border-[#444]" />
                )}
              </span>
              <div className="min-w-0">
                <div>{s.label}</div>
                {s.detail && (
                  <div className="text-[11px] text-[#777] truncate">{s.detail}</div>
                )}
              </div>
            </li>
          ))}
        </ul>

        {fatal && (
          <div className="space-y-3 rounded-sm border border-red-800/60 bg-red-950/40 p-3">
            <p className="text-sm text-red-200">{fatal}</p>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-sm bg-[#333] hover:bg-[#444] text-white"
              onClick={() => setRunId((n) => n + 1)}
            >
              <RefreshCw size={12} />
              Повторить
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default SplashScreen;
