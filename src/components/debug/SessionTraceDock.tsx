// KEEP: session trace — do not remove without explicit user order
import React, { useEffect, useRef, useState } from 'react';
import { Download, Pause, Play, Tag, Trash2, X } from 'lucide-react';
import {
  addEvent,
  clearEvents,
  downloadSessionTraceJson,
  getEvents,
  getTraceSessionId,
  isTraceRecording,
  setRecording,
  subscribe,
  type TraceEvent,
  type TraceKind,
} from '../../debug/sessionTrace';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';

const KIND_COLOR: Record<TraceKind, string> = {
  'ui.click': 'text-sky-300',
  'ui.keydown': 'text-sky-400',
  'ui.tab': 'text-sky-200',
  'api.req': 'text-emerald-400',
  'api.res': 'text-emerald-300',
  'ws.connect': 'text-violet-300',
  'ws.close': 'text-violet-400',
  'ws.error': 'text-red-400',
  'ws.msg': 'text-violet-200',
  'store.change': 'text-amber-300',
  'be.log': 'text-orange-300',
  modal: 'text-red-300',
  note: 'text-[var(--dv-accent)]',
};

function fmtTime(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleTimeString('ru-RU', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
}

type Props = {
  open: boolean;
  onClose: () => void;
};

export const SessionTraceDock: React.FC<Props> = ({ open, onClose }) => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const setAuthenticated = useMuraveiStore((s) => s.setAuthenticated);
  const [rows, setRows] = useState<TraceEvent[]>(() => getEvents());
  const [rec, setRec] = useState(() => isTraceRecording());
  const [beTail, setBeTail] = useState<string[]>([]);
  const [busyTail, setBusyTail] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    return subscribe((ev) => {
      setRows(getEvents());
      if (ev) setRec(isTraceRecording());
    });
  }, []);

  useEffect(() => {
    if (!open || !stickRef.current) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [rows, open]);

  // Merge BE runtime_log into be.log (poll only while authenticated)
  useEffect(() => {
    if (!open || !isAuthenticated) return;
    let cancelled = false;
    let timer: number | null = null;
    const seen = new Set<string>();

    const stop = () => {
      if (timer != null) {
        window.clearInterval(timer);
        timer = null;
      }
    };

    const poll = async () => {
      try {
        const res = await fetch('/api/debug/recent?limit=40', { headers: authHeaders() });
        if (cancelled) return;
        if (res.status === 401) {
          try {
            localStorage.removeItem('muravei-token');
          } catch {
            /* ignore */
          }
          setAuthenticated(false);
          stop();
          return;
        }
        if (!res.ok) return;
        const data = (await res.json()) as {
          entries?: { id?: string; source?: string; message?: string; level?: string }[];
        };
        const allow = new Set(['http', 'ws', 'trace', 'scan', 'recon', 'geo', 'cd', 'gsplat']);
        for (const e of data.entries || []) {
          if (!e.id || seen.has(e.id)) continue;
          if (!allow.has(String(e.source || ''))) continue;
          seen.add(e.id);
          if (seen.size > 400) {
            const drop = [...seen].slice(0, 200);
            for (const id of drop) seen.delete(id);
          }
          const msg = (e.message || '').slice(0, 220);
          if (!msg) continue;
          addEvent('be.log', msg, { source: e.source, level: e.level });
        }
      } catch {
        /* ignore */
      }
    };
    timer = window.setInterval(() => void poll(), 2000);
    void poll();
    return () => {
      cancelled = true;
      stop();
    };
  }, [open, isAuthenticated, setAuthenticated]);

  if (!open) return null;

  const fetchBeTail = async () => {
    setBusyTail(true);
    try {
      const res = await fetch('/api/debug/trace/file?tail=50', { headers: authHeaders() });
      if (!res.ok) {
        setBeTail([`HTTP ${res.status}`]);
        return;
      }
      const data = (await res.json()) as { lines?: string[] };
      setBeTail(data.lines || []);
    } catch (e) {
      setBeTail([e instanceof Error ? e.message : 'error']);
    } finally {
      setBusyTail(false);
    }
  };

  const visible = rows.slice(-80);

  return (
    <div className="fixed bottom-2 right-2 z-[9998] w-[min(480px,96vw)] max-h-[42vh] flex flex-col rounded-sm border border-[var(--dv-border)] bg-black/90 shadow-xl text-[10px] font-mono">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-[var(--dv-border)] bg-[var(--dv-surface)]">
        <span className={rec ? 'text-red-400' : 'text-[var(--dv-muted)]'}>
          {rec ? '● REC' : '⏸ PAUSE'}
        </span>
        <span className="text-[var(--dv-muted)] truncate">
          {getTraceSessionId().slice(0, 8)} · {rows.length}
        </span>
        <div className="flex-1" />
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm hover:bg-[var(--dv-hover)]"
          title={rec ? 'Пауза' : 'Запись'}
          onClick={() => {
            setRecording(!rec);
            setRec(!rec);
          }}
        >
          {rec ? <Pause size={12} /> : <Play size={12} />}
        </button>
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm hover:bg-[var(--dv-hover)]"
          title="Метка"
          onClick={() => addEvent('note', `MARK ${new Date().toISOString()}`)}
        >
          <Tag size={12} />
        </button>
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm hover:bg-[var(--dv-hover)]"
          title="Очистить"
          onClick={() => clearEvents()}
        >
          <Trash2 size={12} />
        </button>
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm hover:bg-[var(--dv-hover)]"
          title="Скачать JSON"
          onClick={() => downloadSessionTraceJson()}
        >
          <Download size={12} />
        </button>
        <button
          type="button"
          className="px-1.5 py-0.5 rounded-sm hover:bg-[var(--dv-hover)] text-[var(--dv-muted)]"
          title="Закрыть dock (код трассировки остаётся)"
          onClick={onClose}
        >
          <X size={12} />
        </button>
      </div>
      <div
        className="flex-1 overflow-auto px-2 py-1 space-y-0.5"
        onScroll={(e) => {
          const el = e.currentTarget;
          stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {visible.map((r) => (
          <div key={r.id} className="leading-tight">
            <span className="text-[var(--dv-muted)]">{fmtTime(r.ts)} </span>
            <span className={KIND_COLOR[r.kind] || ''}>{r.kind}</span>
            <span className="text-[var(--dv-text)]"> {r.summary}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      <div className="border-t border-[var(--dv-border)] px-2 py-1 flex flex-col gap-1">
        <button
          type="button"
          className="self-start px-1.5 py-0.5 rounded-sm border border-[var(--dv-border)] hover:bg-[var(--dv-hover)] disabled:opacity-50"
          disabled={busyTail}
          onClick={() => void fetchBeTail()}
        >
          {busyTail ? '…' : 'BE logs/trace.log ×50'}
        </button>
        {beTail.length > 0 && (
          <pre className="max-h-24 overflow-auto text-[9px] text-orange-200/90 whitespace-pre-wrap">
            {beTail.join('\n')}
          </pre>
        )}
      </div>
    </div>
  );
};

export default SessionTraceDock;
