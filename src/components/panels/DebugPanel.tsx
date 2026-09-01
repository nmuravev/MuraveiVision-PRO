import React, { useEffect, useRef, useState } from 'react';
import { Bug, Download, Trash2 } from 'lucide-react';
import { readSse } from '../../lib/readSse';
import { logger, type LogEntry, type LogLevel } from '../../services/logger';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';

const LEVELS: LogLevel[] = ['error', 'warn', 'info', 'debug', 'verbose'];

const LEVEL_CLASS: Record<LogLevel, string> = {
  error: 'text-red-400',
  warn: 'text-amber-300',
  info: 'text-[var(--dv-text)]',
  debug: 'text-slate-400',
  verbose: 'text-slate-500',
};

type LogOrigin = 'frontend' | 'backend';

type PanelRow = LogEntry & {
  origin: LogOrigin;
  kind?: 'text' | 'cmd' | 'stderr';
};

type DetectStatus = {
  mode?: string;
  model?: string;
  kind?: string;
  last_kind?: string;
  device?: string;
  device_backend?: string;
  cuda_name?: string;
  tier?: string;
  imgsz?: number;
  degraded?: boolean;
  last_inference_ms?: number;
  last_n?: number;
  nms_mode?: string;
  queue_size?: number;
  nc?: number;
};

type BackendLogPayload = {
  id?: string;
  ts?: number;
  level?: string;
  source?: string;
  message?: string;
  kind?: 'text' | 'cmd' | 'stderr';
};

function levelOrder(level: LogLevel): number {
  const order: Record<LogLevel, number> = {
    error: 0,
    warn: 1,
    info: 2,
    debug: 3,
    verbose: 4,
  };
  return order[level];
}

function normalizeLevel(raw: string | undefined): LogLevel {
  if (raw === 'error' || raw === 'warn' || raw === 'info' || raw === 'debug' || raw === 'verbose') {
    return raw;
  }
  return 'info';
}

function toFrontendRow(entry: LogEntry): PanelRow {
  return { ...entry, origin: 'frontend', kind: 'text' };
}

function toBackendRow(payload: BackendLogPayload): PanelRow {
  return {
    id: payload.id || `be-${payload.ts ?? Date.now()}`,
    ts: typeof payload.ts === 'number' ? payload.ts * 1000 : Date.now(),
    level: normalizeLevel(payload.level),
    source: payload.source || 'backend',
    message: payload.message || '',
    origin: 'backend',
    kind: payload.kind || 'text',
  };
}

export const DebugPanel: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [level, setLevel] = useState<LogLevel>('verbose');
  const [originFilter, setOriginFilter] = useState<'all' | LogOrigin>('all');
  const [rows, setRows] = useState<PanelRow[]>(() =>
    logger.getEntries('verbose').map(toFrontendRow),
  );
  const [status, setStatus] = useState<DetectStatus | null>(null);
  const [backendConnected, setBackendConnected] = useState(false);
  const [fps, setFps] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const lastMsRef = useRef(0);
  const lastAtRef = useRef(0);
  const seenBackendIds = useRef(new Set<string>());

  const appendRow = (row: PanelRow) => {
    setRows((prev) => {
      const next = [...prev, row];
      return next.length > 1500 ? next.slice(-1500) : next;
    });
  };

  useEffect(() => {
    return logger.subscribe((entry) => {
      appendRow(toFrontendRow(entry));
    });
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setBackendConnected(false);
      seenBackendIds.current.clear();
      return;
    }

    let cancelled = false;
    const abort = new AbortController();

    void (async () => {
      try {
        const res = await fetch('/api/debug/recent?limit=400', { headers: authHeaders() });
        if (res.ok) {
          const data = (await res.json()) as { entries?: BackendLogPayload[] };
          for (const ev of data.entries || []) {
            const row = toBackendRow(ev);
            if (seenBackendIds.current.has(row.id)) continue;
            seenBackendIds.current.add(row.id);
            appendRow(row);
          }
        }
      } catch {
        /* ignore bootstrap errors */
      }

      while (!cancelled) {
        try {
          setBackendConnected(true);
          await readSse(
            '/api/debug/stream',
            (ev) => {
              const row = toBackendRow(ev as BackendLogPayload);
              if (seenBackendIds.current.has(row.id)) return;
              seenBackendIds.current.add(row.id);
              appendRow(row);
            },
            abort,
          );
        } catch {
          if (cancelled || abort.signal.aborted) break;
          setBackendConnected(false);
          await new Promise((r) => window.setTimeout(r, 2000));
        }
      }
    })();

    return () => {
      cancelled = true;
      abort.abort();
      setBackendConnected(false);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (stickRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [rows, level, originFilter]);

  useEffect(() => {
    if (!isAuthenticated) {
      setStatus(null);
      setFps(0);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch('/api/detect/status', {
          headers: authHeaders(),
        });
        if (!res.ok) return;
        const data = (await res.json()) as DetectStatus;
        if (cancelled) return;
        setStatus(data);
        const ms = Number(data.last_inference_ms || 0);
        const now = Date.now();
        if (ms > 0 && ms !== lastMsRef.current) {
          const dt = (now - lastAtRef.current) / 1000;
          if (lastAtRef.current > 0 && dt > 0.05) {
            setFps(Math.min(60, Number((1 / dt).toFixed(1))));
          }
          lastMsRef.current = ms;
          lastAtRef.current = now;
        } else if (ms <= 0) {
          setFps(0);
        }
      } catch {
        /* ignore poll errors */
      }
    };
    void poll();
    const id = window.setInterval(poll, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [isAuthenticated]);

  const visible = rows.filter((r) => {
    if (originFilter !== 'all' && r.origin !== originFilter) return false;
    return levelOrder(r.level) <= levelOrder(level);
  });

  const exportLogs = () => {
    const text = visible
      .map(
        (e) =>
          `${new Date(e.ts).toISOString()} [${e.origin}] [${e.level}] [${e.source}] ${e.message}`,
      )
      .join('\n');
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `muravei-debug-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    logger.info('debug', 'Логи экспортированы');
  };

  const clearAll = async () => {
    logger.clear();
    seenBackendIds.current.clear();
    setRows([]);
    if (isAuthenticated) {
      try {
        await fetch('/api/debug/clear', { method: 'POST', headers: authHeaders() });
      } catch {
        /* ignore */
      }
    }
  };

  const kind = status?.last_kind || status?.kind || '—';
  const device = status?.device || '—';
  const backend = status?.device_backend || '—';
  const tier = status?.tier || '—';
  const ms = status?.last_inference_ms ?? 0;
  const n = status?.last_n ?? 0;
  const q = status?.queue_size ?? 0;

  return (
    <div className="h-full flex flex-col bg-[var(--dv-panel)] text-xs overflow-hidden">
      <div className="px-2 py-1.5 border-b border-[var(--dv-border)] flex items-center gap-2 flex-shrink-0 flex-wrap">
        <Bug size={13} className="text-[var(--dv-accent)]" />
        <span className="font-semibold text-[11px]">Отладка</span>
        <span
          className={`text-[9px] px-1 py-0.5 rounded ${backendConnected ? 'bg-emerald-900/40 text-emerald-300' : 'bg-amber-900/30 text-amber-300'}`}
          title="Поток логов бэкенда"
        >
          backend {backendConnected ? 'live' : isAuthenticated ? '…' : 'auth'}
        </span>
        <select
          className="bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-1.5 py-0.5 rounded-sm text-[10px]"
          value={originFilter}
          onChange={(e) => setOriginFilter(e.target.value as 'all' | LogOrigin)}
          title="Источник логов"
        >
          <option value="all">все</option>
          <option value="backend">backend</option>
          <option value="frontend">frontend</option>
        </select>
        <select
          className="ml-auto bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] px-1.5 py-0.5 rounded-sm text-[10px]"
          value={level}
          onChange={(e) => setLevel(e.target.value as LogLevel)}
          title="Уровень логов"
        >
          {LEVELS.map((l) => (
            <option key={l} value={l}>
              {l}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="p-1 rounded-sm hover:bg-[#333] text-[var(--dv-text-muted)]"
          title="Очистить логи"
          onClick={() => void clearAll()}
        >
          <Trash2 size={12} />
        </button>
        <button
          type="button"
          className="p-1 rounded-sm hover:bg-[#333] text-[var(--dv-text-muted)]"
          title="Экспорт логов"
          onClick={exportLogs}
        >
          <Download size={12} />
        </button>
      </div>

      <div className="px-2 py-1.5 border-b border-[var(--dv-border)] flex-shrink-0 font-mono text-[10px] text-[var(--dv-text-muted)] space-y-0.5">
        <div className="text-[var(--dv-text)] font-semibold text-[11px]">YOLO live</div>
        <div>
          device={device} · backend={backend} · tier={tier} · imgsz={status?.imgsz ?? '—'}
          {status?.degraded ? ' · DEGRADED' : ''}
        </div>
        <div>
          model={status?.model || '—'} · mode={status?.mode || '—'} · cuda={status?.cuda_name || '—'}
        </div>
        <div>
          kind={kind} · n={n} · {ms}ms · ~{fps} fps · queue={q} · nms={status?.nms_mode || '—'}
        </div>
      </div>

      <div
        className="flex-1 overflow-auto font-mono text-[10px] p-2 space-y-0.5"
        onScroll={(e) => {
          const el = e.currentTarget;
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {!isAuthenticated && (
          <div className="text-amber-300 mb-2">
            Войдите в систему — иначе не видны команды бэкенда (ffmpeg, YOLO scan, COLMAP).
          </div>
        )}
        {visible.length === 0 && (
          <div className="text-[var(--dv-text-muted)]">Логов пока нет</div>
        )}
        {visible.map((r) => {
          const isCmd = r.kind === 'cmd' || r.message.startsWith('$ ');
          const isStderr = r.kind === 'stderr';
          return (
            <div
              key={`${r.origin}-${r.id}`}
              className={`leading-snug ${isCmd ? 'text-emerald-300' : isStderr ? 'text-orange-300' : LEVEL_CLASS[r.level]}`}
            >
              <span className="text-slate-500">{new Date(r.ts).toLocaleTimeString()}</span>{' '}
              <span className="uppercase">[{r.level}]</span>{' '}
              <span className="text-slate-400">
                [{r.origin}/{r.source}]
              </span>{' '}
              {r.message}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};

export default DebugPanel;
