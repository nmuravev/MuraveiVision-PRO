import type { HudZones } from '../../hooks/useHudZones';

type Props = {
  zones: HudZones | null;
  onDisable?: () => void;
};

/** Semi-transparent HUD exclusion rects + badge (relative % only). */
export function HudExclusionOverlay({ zones, onDisable }: Props) {
  if (!zones?.ready) return null;
  const { top, bottom, left, right } = zones;
  if (top <= 0 && bottom <= 0 && left <= 0 && right <= 0) return null;

  const parts: string[] = [];
  if (top > 0) parts.push(`верх ~${Math.round(top * 100)}%`);
  if (bottom > 0) parts.push(`низ ~${Math.round(bottom * 100)}%`);
  if (left > 0) parts.push(`лево ~${Math.round(left * 100)}%`);
  if (right > 0) parts.push(`право ~${Math.round(right * 100)}%`);

  return (
    <>
      {top > 0 && (
        <div
          className="pointer-events-none absolute left-0 right-0 top-0 bg-amber-500/25 border-b border-amber-400/40"
          style={{ height: `${top * 100}%` }}
          data-testid="hud-band-top"
        />
      )}
      {bottom > 0 && (
        <div
          className="pointer-events-none absolute left-0 right-0 bottom-0 bg-amber-500/25 border-t border-amber-400/40"
          style={{ height: `${bottom * 100}%` }}
          data-testid="hud-band-bottom"
        />
      )}
      {left > 0 && (
        <div
          className="pointer-events-none absolute top-0 bottom-0 left-0 bg-amber-500/20 border-r border-amber-400/40"
          style={{ width: `${left * 100}%` }}
        />
      )}
      {right > 0 && (
        <div
          className="pointer-events-none absolute top-0 bottom-0 right-0 bg-amber-500/20 border-l border-amber-400/40"
          style={{ width: `${right * 100}%` }}
        />
      )}
      <div
        className="absolute top-1 left-1 z-10 flex items-center gap-1 rounded-sm bg-black/70 px-1.5 py-0.5 text-[10px] text-amber-200"
        data-testid="hud-badge"
      >
        <span>HUD исключён: {parts.join(', ')}</span>
        {onDisable && (
          <button
            type="button"
            className="ml-1 underline text-amber-100/80 hover:text-white"
            onClick={onDisable}
            title="Отключить HUD-исключение для этого видео"
          >
            выкл
          </button>
        )}
      </div>
    </>
  );
}
