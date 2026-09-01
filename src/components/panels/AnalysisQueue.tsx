import React, { useState } from 'react';
import { Download, ListPlus, Trash2 } from 'lucide-react';
import { useTimelineStore } from '../../store/timeline-store';
import { useViewerStore } from '../../store/useViewerStore';
import { downloadAuthorized } from '../../lib/download';
import { logger } from '../../services/logger';

function formatClock(sec: number): string {
  const m = Math.floor(Math.max(0, sec) / 60);
  const s = Math.max(0, sec) % 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(2).padStart(5, '0')}`;
}

function parseClock(value: string): number | null {
  const t = value.trim().replace(',', '.');
  if (!t) return null;
  if (/^\d+(\.\d+)?$/.test(t)) return Number(t);
  const parts = t.split(':');
  if (parts.length < 2 || parts.length > 3) return null;
  const nums = parts.map((p) => Number(p));
  if (nums.some((n) => Number.isNaN(n))) return null;
  if (parts.length === 2) return nums[0] * 60 + nums[1];
  return nums[0] * 3600 + nums[1] * 60 + nums[2];
}

function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() || path;
}

const TimeField: React.FC<{
  value: number;
  onCommit: (next: number) => void;
}> = ({ value, onCommit }) => {
  const [draft, setDraft] = useState(formatClock(value));
  const [focused, setFocused] = useState(false);
  const shown = focused ? draft : formatClock(value);

  return (
    <input
      className="w-[72px] bg-[var(--dv-bg-deep)] border border-[var(--dv-border)] rounded-sm px-1 py-0.5 font-mono text-[10px] text-[var(--dv-text)]"
      value={shown}
      onFocus={() => {
        setDraft(formatClock(value));
        setFocused(true);
      }}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        setFocused(false);
        const parsed = parseClock(draft);
        if (parsed == null) {
          setDraft(formatClock(value));
          return;
        }
        onCommit(parsed);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter') (e.currentTarget as HTMLInputElement).blur();
      }}
    />
  );
};

export const AnalysisQueue: React.FC = () => {
  const analysisQueue = useTimelineStore((s) => s.analysisQueue);
  const inPoint = useTimelineStore((s) => s.inPoint);
  const outPoint = useTimelineStore((s) => s.outPoint);
  const mediaDuration = useTimelineStore((s) => s.mediaDuration);
  const playheadPosition = useTimelineStore((s) => s.playheadPosition);
  const markIn = useTimelineStore((s) => s.markIn);
  const markOut = useTimelineStore((s) => s.markOut);
  const enqueueRange = useTimelineStore((s) => s.enqueueRange);
  const removeQueued = useTimelineStore((s) => s.removeQueued);
  const updateQueued = useTimelineStore((s) => s.updateQueued);
  const seekTo = useTimelineStore((s) => s.seekTo);
  const focusedViewerId = useViewerStore((s) => s.focusedViewerId);
  const sourcePath = useViewerStore(
    (s) => s.viewers[focusedViewerId]?.sourcePath ?? s.viewers['viewer-1']?.sourcePath,
  );
  const [hint, setHint] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const hasRange = inPoint != null && outPoint != null && outPoint > inPoint;

  const addJob = () => {
    setHint(null);
    if (!sourcePath) {
      setHint('Нет видео во Viewer. Перетащите файл из Media Pool.');
      return;
    }
    let start = inPoint;
    let end = outPoint;
    if (start == null || end == null || end <= start) {
      const dur = mediaDuration > 0 ? mediaDuration : 0;
      if (dur > 0) {
        start = start ?? 0;
        end = end != null && end > start ? end : dur;
        if (end <= start) {
          start = 0;
          end = dur;
        }
      } else {
        start = 0;
        end = Math.max(playheadPosition + 5, 1);
      }
      markIn(start);
      markOut(end);
    }
    const ok = enqueueRange(sourcePath, { inPoint: start!, outPoint: end! });
    if (!ok) {
      setHint('Не удалось добавить. Проверьте In < Out.');
      return;
    }
    setHint(`Добавлен фрагмент ${formatClock(start!)}–${formatClock(end!)}`);
    logger.info('queue', `Фрагмент + ${formatClock(start!)}–${formatClock(end!)}`);
  };

  const exportZip = async () => {
    if (analysisQueue.length === 0) {
      setHint('Очередь пуста — сначала добавьте фрагменты');
      return;
    }
    setExporting(true);
    setHint(null);
    try {
      await downloadAuthorized('/api/export/queue-zip', {
        method: 'POST',
        body: {
          fragments: analysisQueue.map((j) => ({
            source: j.sourcePath,
            in: j.inPoint,
            out: j.outPoint,
          })),
        },
        filename: `muravei-queue-${Date.now()}.zip`,
      });
      setHint(`Экспортировано ${analysisQueue.length} фрагмент(ов) в ZIP`);
      logger.info('queue', `ZIP экспорт n=${analysisQueue.length}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Ошибка экспорта';
      setHint(msg);
      logger.error('queue', msg);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-[var(--dv-panel)] text-[11px]">
      <div className="flex items-center gap-2 px-2 py-1.5 border-b border-[var(--dv-border)]">
        <span className="uppercase tracking-wider text-[10px] text-[var(--dv-text-muted)]">
          Очередь
        </span>
        <span className="text-[10px] font-mono text-amber-400">
          {analysisQueue.length} фрагмент
          {analysisQueue.length === 1 ? '' : analysisQueue.length >= 2 && analysisQueue.length <= 4 ? 'а' : 'ов'}
        </span>
        <div className="flex-1" />
        <button
          type="button"
          className="px-1.5 py-0.5 rounded flex items-center gap-1 text-[10px] bg-[#333] hover:bg-amber-900 text-amber-300"
          title={hasRange ? 'Добавить текущий In/Out' : 'Без I/O добавится весь ролик'}
          onClick={addJob}
        >
          <ListPlus size={11} />
          Добавить
        </button>
        <button
          type="button"
          disabled={exporting || analysisQueue.length === 0}
          className="px-1.5 py-0.5 rounded flex items-center gap-1 text-[10px] bg-[var(--dv-accent)] text-black font-medium disabled:opacity-40"
          title="Нарезать фрагменты и скачать ZIP для инженера"
          onClick={() => void exportZip()}
        >
          <Download size={11} />
          {exporting ? 'ZIP…' : 'Экспорт ZIP'}
        </button>
      </div>
      <div className="px-2 py-1 text-[10px] text-[var(--dv-text-muted)] border-b border-[var(--dv-border)]">
        In/Out на таймлайне → «Добавить» → «Экспорт ZIP» (нарезка для инженера, без пакетного YOLO).
      </div>
      {hint && (
        <div className="px-2 py-1 text-[10px] text-amber-300 border-b border-[var(--dv-border)]">
          {hint}
        </div>
      )}
      <div className="flex-1 overflow-auto p-2 space-y-1.5">
        {analysisQueue.length === 0 ? (
          <div className="text-[10px] text-[var(--dv-text-muted)] px-1 py-4 text-center">
            Очередь пуста
          </div>
        ) : (
          analysisQueue.map((job, idx) => (
            <div
              key={job.id}
              className="border border-[var(--dv-border)] bg-[var(--dv-bg-deep)] px-2 py-1.5"
            >
              <button
                type="button"
                className="w-full text-left text-[10px] text-[var(--dv-text)] truncate hover:text-[var(--dv-accent)]"
                title={job.sourcePath}
                onClick={() => seekTo(job.inPoint)}
              >
                #{idx + 1} {basename(job.sourcePath)}
              </button>
              <div className="mt-1 flex items-center gap-1">
                <span className="text-[9px] text-blue-300 font-mono w-3">I</span>
                <TimeField
                  value={job.inPoint}
                  onCommit={(next) => updateQueued(job.id, { inPoint: next })}
                />
                <span className="text-[9px] text-red-300 font-mono w-3">O</span>
                <TimeField
                  value={job.outPoint}
                  onCommit={(next) => updateQueued(job.id, { outPoint: next })}
                />
                <span className="text-[9px] font-mono text-[var(--dv-text-muted)] ml-auto">
                  {formatClock(Math.max(0, job.outPoint - job.inPoint))}
                </span>
                <button
                  type="button"
                  className="p-0.5 text-gray-500 hover:text-red-400"
                  title="Удалить из очереди"
                  onClick={() => removeQueued(job.id)}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default AnalysisQueue;
