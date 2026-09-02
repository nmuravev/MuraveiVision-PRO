import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Radio, Wifi } from 'lucide-react';
import { classLabelRu } from '../../lib/classLabels';
import { formatMediaTime, mediaPathsMatch } from '../../lib/mediaPaths';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { Modal } from '../ui';

export type TimelineEventType = 'local_detection' | 'network_target';

export interface TimelineEvent {
  id: string;
  type: TimelineEventType;
  time_sec: number | null;
  class_name: string;
  confidence: number;
  source_video: string | null;
  source_base: string | null;
  created_at: number;
  gps_lat?: number | null;
  gps_lon?: number | null;
  notes?: string | null;
}

type FilterKey = 'all' | 'local' | 'network' | `class:${string}`;

const POLL_MS = 3000;
const CLASS_COLORS: Record<string, string> = {
  tank: '#ef4444',
  armored_vehicle: '#f97316',
  military_truck: '#fb923c',
  uav: '#eab308',
  quadcopter_drone: '#eab308',
  fpv_drone: '#eab308',
  soldier: '#22c55e',
  artillery: '#a855f7',
  mine: '#f43f5e',
  anti_tank_mine: '#f43f5e',
  anti_personnel_mine: '#f43f5e',
  default: '#64748b',
};

function classColor(name: string): string {
  return CLASS_COLORS[name] || CLASS_COLORS.default;
}

function typeLabel(type: TimelineEventType): string {
  return type === 'network_target' ? 'Сеть' : 'Локально';
}

function clockLabel(ts: number): string {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export const EventTimeline: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const setFocusedViewer = useViewerStore((s) => s.setFocusedViewer);
  const viewers = useViewerStore((s) => s.viewers);

  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [autoScroll, setAutoScroll] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [detail, setDetail] = useState<TimelineEvent | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const topIdRef = useRef<string | null>(null);

  const load = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/events/timeline?window=300&limit=50', {
        headers: authHeaders(),
      });
      if (!res.ok) {
        setError(`timeline ${res.status}`);
        return;
      }
      const body = (await res.json()) as { events?: TimelineEvent[] };
      setEvents(Array.isArray(body.events) ? body.events : []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка ленты');
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) return;
    void load();
    const t = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(t);
  }, [isAuthenticated, load]);

  const classNames = useMemo(() => {
    const set = new Set<string>();
    for (const ev of events) {
      if (ev.class_name) set.add(ev.class_name);
    }
    return [...set].sort();
  }, [events]);

  const visible = useMemo(() => {
    return events.filter((ev) => {
      if (filter === 'local') return ev.type === 'local_detection';
      if (filter === 'network') return ev.type === 'network_target';
      if (filter.startsWith('class:')) return ev.class_name === filter.slice(6);
      return true;
    });
  }, [events, filter]);

  useEffect(() => {
    const top = visible[0]?.id ?? null;
    if (!autoScroll || !top || top === topIdRef.current) {
      topIdRef.current = top;
      return;
    }
    topIdRef.current = top;
    listRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
  }, [visible, autoScroll]);

  const onEventClick = (ev: TimelineEvent) => {
    if (ev.type === 'network_target') {
      setDetail(ev);
      return;
    }
    const matchId = Object.entries(viewers).find(([, st]) =>
      mediaPathsMatch(st?.sourcePath || '', ev.source_video || ''),
    )?.[0];
    if (matchId) setFocusedViewer(matchId);
    if (typeof ev.time_sec === 'number') seekTo(ev.time_sec);
  };

  return (
    <div
      data-testid="event-timeline"
      className="h-full w-full flex flex-col bg-dv-deep text-[11px] text-dv-text"
    >
      <div className="flex items-center gap-2 px-2 py-1 border-b border-dv-border shrink-0">
        <span className="uppercase tracking-wider text-[9px] text-dv-muted font-semibold">
          Лента
        </span>
        <select
          data-testid="event-timeline-filter"
          aria-label="Фильтр событий"
          className="bg-dv-surface border border-dv-border px-1 py-0.5 text-[10px] text-dv-text max-w-[10rem]"
          value={filter}
          onChange={(e) => setFilter(e.target.value as FilterKey)}
        >
          <option value="all">Все</option>
          <option value="local">Только локальные</option>
          <option value="network">Только сеть</option>
          {classNames.map((name) => (
            <option key={name} value={`class:${name}`}>
              {classLabelRu(undefined, name, [])}
            </option>
          ))}
        </select>
        <label className="ml-auto inline-flex items-center gap-1 text-[10px] text-dv-muted cursor-pointer">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
          />
          Авто-скролл
        </label>
      </div>
      {!isAuthenticated ? (
        <div className="p-3 text-dv-muted">Войдите, чтобы видеть события.</div>
      ) : (
        <div ref={listRef} className="flex-1 min-h-0 overflow-auto font-mono" data-testid="event-timeline-list">
          {error && <div className="px-2 py-1 text-dv-danger">{error}</div>}
          {visible.length === 0 && !error && (
            <div className="px-2 py-3 text-dv-muted">Нет событий за последние 5 мин.</div>
          )}
          {visible.map((ev) => {
            const color = classColor(ev.class_name);
            const isNet = ev.type === 'network_target';
            return (
              <button
                key={ev.id}
                type="button"
                data-testid={`event-${ev.id}`}
                data-event-type={ev.type}
                className="w-full text-left px-2 py-1 border-b border-dv-border/60 hover:bg-dv-hover flex items-center gap-2"
                onClick={() => onEventClick(ev)}
              >
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: color }}
                />
                {isNet ? (
                  <Wifi size={10} className="text-amber-400 shrink-0" />
                ) : (
                  <Radio size={10} className="text-dv-accent shrink-0" />
                )}
                <span className="text-[9px] uppercase tracking-wide text-dv-muted w-16 shrink-0">
                  {typeLabel(ev.type)}
                </span>
                <span className="text-dv-text truncate" style={{ color }}>
                  {classLabelRu(undefined, ev.class_name, []) || ev.class_name || '—'}
                </span>
                <span className="text-dv-muted ml-auto shrink-0 tabular-nums">
                  {isNet
                    ? clockLabel(ev.created_at)
                    : typeof ev.time_sec === 'number'
                      ? formatMediaTime(ev.time_sec)
                      : clockLabel(ev.created_at)}
                </span>
                <span className="text-dv-muted shrink-0 w-10 text-right">
                  {Math.round((ev.confidence || 0) * 100)}%
                </span>
              </button>
            );
          })}
        </div>
      )}
      <Modal
        open={Boolean(detail)}
        title="Сетевая цель"
        onClose={() => setDetail(null)}
      >
        {detail && (
          <div data-testid="event-network-detail" className="space-y-1.5 text-[12px] text-dv-text">
            <div>
              <span className="text-dv-muted">Класс: </span>
              {classLabelRu(undefined, detail.class_name, []) || detail.class_name}
            </div>
            <div>
              <span className="text-dv-muted">База: </span>
              {detail.source_base || '—'}
            </div>
            <div>
              <span className="text-dv-muted">GPS: </span>
              {detail.gps_lat != null && detail.gps_lon != null
                ? `${detail.gps_lat.toFixed(5)}, ${detail.gps_lon.toFixed(5)}`
                : '—'}
            </div>
            <div>
              <span className="text-dv-muted">Видео: </span>
              {detail.source_video || '—'}
            </div>
            <div>
              <span className="text-dv-muted">Заметки: </span>
              {detail.notes || '—'}
            </div>
            <p className="text-[10px] text-dv-muted pt-1">
              Удалённый ролик недоступен — seek не выполняется.
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default EventTimeline;
