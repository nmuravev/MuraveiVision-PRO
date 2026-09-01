import React, { useRef, useCallback } from 'react';
import { usePanelLayoutStore } from '../store/usePanelLayoutStore';
import { ComponentForId } from '../components/ComponentRegistry';
import { PanelChrome } from './PanelChrome';

export const FloatingPanelHost: React.FC = () => {
  const floatingPanels = usePanelLayoutStore((s) => s.floatingPanels);
  const updateFloating = usePanelLayoutStore((s) => s.updateFloating);
  const dragRef = useRef<{
    id: string;
    ox: number;
    oy: number;
    sx: number;
    sy: number;
  } | null>(null);

  const onPointerDown = useCallback(
    (e: React.PointerEvent, id: string, x: number, y: number) => {
      const target = e.target as HTMLElement;
      if (!target.closest('.panel-chrome__header')) return;
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      dragRef.current = { id, ox: e.clientX, oy: e.clientY, sx: x, sy: y };
    },
    [],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const nx = Math.max(0, d.sx + (e.clientX - d.ox));
      const ny = Math.max(0, d.sy + (e.clientY - d.oy));
      updateFloating(d.id as never, { x: nx, y: ny });
    },
    [updateFloating],
  );

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  return (
    <>
      {floatingPanels.map((p) => (
        <div
          key={p.id}
          className="floating-panel-window"
          style={{ left: p.x, top: p.y, width: p.w, height: p.h }}
          onPointerDown={(e) => onPointerDown(e, p.id, p.x, p.y)}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <PanelChrome id={p.id} floating>
            <ComponentForId id={p.id} />
          </PanelChrome>
        </div>
      ))}
    </>
  );
};

export default FloatingPanelHost;
