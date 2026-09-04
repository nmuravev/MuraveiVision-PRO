import React, { useEffect, useRef } from 'react';

export type HeatmapOverlayProps = {
  heatmapB64: string;
  opacity?: number;
  visible?: boolean;
};

/**
 * Full-bleed change-diff heatmap under SVG bbox overlays (Compare mode).
 */
export const HeatmapOverlay: React.FC<HeatmapOverlayProps> = ({
  heatmapB64,
  opacity = 0.5,
  visible = true,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  const draw = () => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img || !img.complete) return;
    const parent = canvas.parentElement;
    const w = Math.max(1, Math.floor(parent?.clientWidth || canvas.clientWidth || 1));
    const h = Math.max(1, Math.floor(parent?.clientHeight || canvas.clientHeight || 1));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    ctx.globalAlpha = opacity;
    ctx.drawImage(img, 0, 0, w, h);
    ctx.globalAlpha = 1;
  };

  useEffect(() => {
    if (!visible || !heatmapB64) {
      imgRef.current = null;
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx?.clearRect(0, 0, canvas.width, canvas.height);
      }
      return;
    }
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      draw();
    };
    img.src = `data:image/png;base64,${heatmapB64}`;
    return () => {
      img.onload = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- redraw via draw when src changes
  }, [heatmapB64, visible]);

  useEffect(() => {
    draw();
  }, [opacity, visible]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!parent || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => draw());
    ro.observe(parent);
    return () => ro.disconnect();
  }, [heatmapB64, opacity, visible]);

  if (!visible || !heatmapB64) return null;

  return (
    <canvas
      ref={canvasRef}
      data-testid="change-heatmap"
      className="absolute inset-0 w-full h-full pointer-events-none"
      aria-hidden
    />
  );
};

export default HeatmapOverlay;
