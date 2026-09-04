import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Eye } from 'lucide-react';
import { clampHudMargin, type HudMargins, type HudZones } from '../../hooks/useHudZones';

type Side = 'top' | 'bottom' | 'left' | 'right';

type Props = {
  /** When true, show HUD chip even if all margins are 0 (after «Сброс»). */
  visible: boolean;
  zones: HudZones | null;
  busy?: boolean;
  onApply: (margins: HudMargins) => void | Promise<void>;
  onAuto: () => void | Promise<void>;
  onReset: () => void | Promise<void>;
};

const EMPTY: HudMargins = { top: 0, bottom: 0, left: 0, right: 0 };

function marginsFromZones(zones: HudZones | null): HudMargins {
  if (!zones) return { ...EMPTY };
  return {
    top: clampHudMargin(zones.top),
    bottom: clampHudMargin(zones.bottom),
    left: clampHudMargin(zones.left),
    right: clampHudMargin(zones.right),
  };
}

function pctLabel(v: number): string {
  return `${Math.round(v * 100)}%`;
}

/** Semi-transparent HUD exclusion bands + collapsible badge; edit mode with drag + sliders. */
export function HudExclusionOverlay({
  visible,
  zones,
  busy = false,
  onApply,
  onAuto,
  onReset,
}: Props) {
  /** Collapsed by default so the amber chip does not cover the overview. */
  const [panelOpen, setPanelOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<HudMargins>(EMPTY);
  const [saving, setSaving] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ side: Side; start: number; origin: number } | null>(null);

  useEffect(() => {
    if (!editing) setDraft(marginsFromZones(zones));
  }, [zones, editing]);

  const enterEdit = () => {
    setDraft(marginsFromZones(zones));
    setEditing(true);
    setPanelOpen(true);
  };

  const cancelEdit = () => {
    setDraft(marginsFromZones(zones));
    setEditing(false);
  };

  const togglePanel = () => {
    if (panelOpen && editing) cancelEdit();
    setPanelOpen((open) => !open);
  };

  const run = async (fn: () => void | Promise<void>) => {
    setSaving(true);
    try {
      await fn();
    } finally {
      setSaving(false);
    }
  };

  const setSide = useCallback((side: Side, value: number) => {
    setDraft((prev) => ({ ...prev, [side]: clampHudMargin(value) }));
  }, []);

  const onPointerDown = (side: Side, e: React.PointerEvent) => {
    if (!editing || busy || saving) return;
    e.preventDefault();
    e.stopPropagation();
    const el = stageRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const start = side === 'top' || side === 'bottom' ? e.clientY : e.clientX;
    dragRef.current = { side, start, origin: draft[side] };
    (e.target as HTMLElement).setPointerCapture(e.pointerId);

    const onMove = (ev: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      let next = d.origin;
      if (d.side === 'top') {
        next = (ev.clientY - rect.top) / rect.height;
      } else if (d.side === 'bottom') {
        next = (rect.bottom - ev.clientY) / rect.height;
      } else if (d.side === 'left') {
        next = (ev.clientX - rect.left) / rect.width;
      } else {
        next = (rect.right - ev.clientX) / rect.width;
      }
      setSide(d.side, next);
    };
    const onUp = (ev: PointerEvent) => {
      dragRef.current = null;
      try {
        (e.target as HTMLElement).releasePointerCapture(ev.pointerId);
      } catch {
        /* ignore */
      }
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  if (!visible) return null;

  const show = editing ? draft : marginsFromZones(zones);
  const { top, bottom, left, right } = show;
  const hasBands = top > 0 || bottom > 0 || left > 0 || right > 0;
  const pending = zones && (!zones.ready || zones.source === 'pending');
  const source = zones?.source ?? '—';

  const parts: string[] = [];
  if (top > 0) parts.push(`верх ~${pctLabel(top)}`);
  if (bottom > 0) parts.push(`низ ~${pctLabel(bottom)}`);
  if (left > 0) parts.push(`лево ~${pctLabel(left)}`);
  if (right > 0) parts.push(`право ~${pctLabel(right)}`);

  const bandClass = editing ? 'pointer-events-auto' : 'pointer-events-none';

  return (
    <div
      ref={stageRef}
      className="absolute inset-0 z-10 pointer-events-none"
      data-testid="hud-overlay-root"
    >
      {(editing || hasBands) && (
        <>
          {(editing || top > 0) && (
            <div
              className={`absolute left-0 right-0 top-0 bg-amber-500/25 border-b border-amber-400/50 ${bandClass}`}
              style={{ height: `${Math.max(top, editing ? 0.008 : 0) * 100}%` }}
              data-testid="hud-band-top"
            >
              {editing && (
                <div
                  className="absolute left-0 right-0 bottom-0 h-2 cursor-ns-resize bg-amber-300/40 hover:bg-amber-200/70 pointer-events-auto"
                  onPointerDown={(e) => onPointerDown('top', e)}
                  title="Потяните границу сверху"
                />
              )}
            </div>
          )}
          {(editing || bottom > 0) && (
            <div
              className={`absolute left-0 right-0 bottom-0 bg-amber-500/25 border-t border-amber-400/50 ${bandClass}`}
              style={{ height: `${Math.max(bottom, editing ? 0.008 : 0) * 100}%` }}
              data-testid="hud-band-bottom"
            >
              {editing && (
                <div
                  className="absolute left-0 right-0 top-0 h-2 cursor-ns-resize bg-amber-300/40 hover:bg-amber-200/70 pointer-events-auto"
                  onPointerDown={(e) => onPointerDown('bottom', e)}
                  title="Потяните границу снизу"
                />
              )}
            </div>
          )}
          {(editing || left > 0) && (
            <div
              className={`absolute top-0 bottom-0 left-0 bg-amber-500/20 border-r border-amber-400/50 ${bandClass}`}
              style={{ width: `${Math.max(left, editing ? 0.008 : 0) * 100}%` }}
              data-testid="hud-band-left"
            >
              {editing && (
                <div
                  className="absolute top-0 bottom-0 right-0 w-2 cursor-ew-resize bg-amber-300/40 hover:bg-amber-200/70 pointer-events-auto"
                  onPointerDown={(e) => onPointerDown('left', e)}
                  title="Потяните границу слева"
                />
              )}
            </div>
          )}
          {(editing || right > 0) && (
            <div
              className={`absolute top-0 bottom-0 right-0 bg-amber-500/20 border-l border-amber-400/50 ${bandClass}`}
              style={{ width: `${Math.max(right, editing ? 0.008 : 0) * 100}%` }}
              data-testid="hud-band-right"
            >
              {editing && (
                <div
                  className="absolute top-0 bottom-0 left-0 w-2 cursor-ew-resize bg-amber-300/40 hover:bg-amber-200/70 pointer-events-auto"
                  onPointerDown={(e) => onPointerDown('right', e)}
                  title="Потяните границу справа"
                />
              )}
            </div>
          )}
        </>
      )}

      <div
        className="absolute top-1 left-1 z-20 flex flex-col gap-1 max-w-[min(100%,22rem)] pointer-events-auto"
        data-testid="hud-badge"
        onPointerDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-1">
          <button
            type="button"
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm bg-black/75 text-amber-200 hover:text-white hover:bg-black/90"
            aria-expanded={panelOpen}
            aria-controls="hud-exclusion-panel"
            title={panelOpen ? 'Свернуть' : 'HUD исключение'}
            aria-label={panelOpen ? 'Свернуть' : 'HUD исключение'}
            data-testid="hud-badge-toggle"
            onClick={togglePanel}
          >
            <Eye size={14} strokeWidth={2} aria-hidden />
          </button>

          {panelOpen && (
            <div
              id="hud-exclusion-panel"
              className="flex flex-wrap items-center gap-1 rounded-sm bg-black/75 px-1.5 py-0.5 text-[10px] text-amber-200"
              data-testid="hud-badge-panel"
            >
              <span className="font-semibold text-amber-100">HUD</span>
              {pending ? (
                <span className="text-amber-200/80">определение…</span>
              ) : hasBands ? (
                <span title={`source=${source}`}>
                  исключён: {parts.join(', ')}
                  {source && source !== '—' ? ` · ${source}` : ''}
                </span>
              ) : (
                <span className="text-amber-200/80">выкл (нет полос)</span>
              )}
              {!editing && (
                <>
                  <button
                    type="button"
                    className="ml-0.5 underline text-amber-100/90 hover:text-white"
                    onClick={enterEdit}
                    disabled={busy || saving}
                    title="Ручная правка краевых полос (0–35%)"
                  >
                    правка
                  </button>
                  {hasBands && (
                    <button
                      type="button"
                      className="underline text-amber-100/80 hover:text-white"
                      onClick={() => void run(onReset)}
                      disabled={busy || saving}
                      title="Сбросить HUD-исключение для этого видео"
                    >
                      сброс
                    </button>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {panelOpen && editing && (
          <div className="rounded-sm bg-black/85 border border-amber-500/40 px-2 py-1.5 text-[10px] text-amber-100 space-y-1.5 shadow-lg">
            {(['top', 'bottom', 'left', 'right'] as const).map((side) => {
              const labels = { top: 'Верх', bottom: 'Низ', left: 'Лево', right: 'Право' };
              return (
                <label key={side} className="flex items-center gap-2">
                  <span className="w-8 shrink-0 text-amber-200/90">{labels[side]}</span>
                  <input
                    type="range"
                    min={0}
                    max={35}
                    step={1}
                    value={Math.round(draft[side] * 100)}
                    disabled={busy || saving}
                    onChange={(e) => setSide(side, Number(e.target.value) / 100)}
                    className="flex-1 min-w-0 accent-amber-400"
                  />
                  <span className="w-8 text-right font-mono tabular-nums">{pctLabel(draft[side])}</span>
                </label>
              );
            })}
            <div className="flex flex-wrap gap-1.5 pt-0.5">
              <button
                type="button"
                className="px-1.5 py-0.5 rounded-sm bg-amber-500/90 text-black font-semibold hover:bg-amber-400 disabled:opacity-40"
                disabled={busy || saving}
                onClick={() =>
                  void run(async () => {
                    await onApply(draft);
                    setEditing(false);
                  })
                }
              >
                Применить
              </button>
              <button
                type="button"
                className="px-1.5 py-0.5 rounded-sm bg-dv-surface text-amber-100 hover:bg-dv-hover disabled:opacity-40"
                disabled={busy || saving}
                onClick={() =>
                  void run(async () => {
                    await onAuto();
                    setEditing(false);
                  })
                }
              >
                Авто
              </button>
              <button
                type="button"
                className="px-1.5 py-0.5 rounded-sm bg-dv-surface text-amber-100 hover:bg-dv-hover disabled:opacity-40"
                disabled={busy || saving}
                onClick={() =>
                  void run(async () => {
                    await onReset();
                    setDraft({ ...EMPTY });
                    setEditing(false);
                  })
                }
              >
                Сброс
              </button>
              <button
                type="button"
                className="px-1.5 py-0.5 rounded-sm text-amber-200/70 hover:text-white underline disabled:opacity-40"
                disabled={busy || saving}
                onClick={cancelEdit}
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
