import { authHeaders, detectionCropSrc } from '../store/useMuraveiStore';
import { mediaPathsMatch } from './mediaPaths';
import type { PersistedDetection } from '../types/muravei';

export function dataUrlToBase64(dataUrl: string): string | null {
  const comma = dataUrl.indexOf(',');
  if (comma < 0) return dataUrl.trim() || null;
  return dataUrl.slice(comma + 1).trim() || null;
}

export async function fetchDetectionCropBase64(detectionId: string): Promise<string | null> {
  try {
    const url = detectionCropSrc(detectionId, null);
    const res = await fetch(url, { headers: authHeaders() });
    if (!res.ok) return null;
    const blob = await res.blob();
    return await new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = () => {
        const raw = String(reader.result || '');
        resolve(dataUrlToBase64(raw));
      };
      reader.onerror = () => resolve(null);
      reader.readAsDataURL(blob);
    });
  } catch {
    return null;
  }
}

export async function fetchVideoFrameBase64(
  sourcePath: string,
  timeSec: number,
): Promise<string | null> {
  try {
    const params = new URLSearchParams({
      path: sourcePath,
      t: String(Math.max(0, timeSec)),
    });
    const res = await fetch(`/api/media/frame?${params}`, { headers: authHeaders() });
    if (!res.ok) return null;
    const data = (await res.json()) as { image_base64?: string };
    return typeof data.image_base64 === 'string' ? data.image_base64 : null;
  } catch {
    return null;
  }
}

export function nearestDetectionAtPlayhead(
  detections: PersistedDetection[],
  sourcePath: string | null | undefined,
  playheadSec: number,
  windowSec = 2.0,
): PersistedDetection | null {
  if (!sourcePath) return null;
  let best: PersistedDetection | null = null;
  let bestDt = windowSec + 1;
  for (const d of detections) {
    if (d.is_deleted) continue;
    if (!mediaPathsMatch(d.source_video || '', sourcePath)) continue;
    const dt = Math.abs(d.time_sec - playheadSec);
    if (dt <= windowSec && dt < bestDt) {
      best = d;
      bestDt = dt;
    }
  }
  return best;
}

export type VisionImageSource =
  | 'detection'
  | 'playhead-detection'
  | 'preview'
  | 'video-frame'
  | 'none';

export async function resolveVisionImage(opts: {
  activeDetectionId?: string | null;
  detections: PersistedDetection[];
  sourcePath?: string | null;
  playheadSec: number;
  previewFrame?: string | null;
}): Promise<{ base64: string | null; source: VisionImageSource; label: string }> {
  const { activeDetectionId, detections, sourcePath, playheadSec, previewFrame } = opts;

  const active = activeDetectionId
    ? detections.find((d) => d.id === activeDetectionId && !d.is_deleted)
    : undefined;
  if (active?.id) {
    const base64 = await fetchDetectionCropBase64(active.id);
    if (base64) {
      return {
        base64,
        source: 'detection',
        label: active.class_name || active.id,
      };
    }
  }

  const near = nearestDetectionAtPlayhead(detections, sourcePath, playheadSec);
  if (near?.id && near.id !== active?.id) {
    const base64 = await fetchDetectionCropBase64(near.id);
    if (base64) {
      return {
        base64,
        source: 'playhead-detection',
        label: `${near.class_name || near.id} @ ${near.time_sec.toFixed(1)}s`,
      };
    }
  }

  if (previewFrame) {
    const base64 = dataUrlToBase64(previewFrame);
    if (base64) {
      return { base64, source: 'preview', label: 'текущий кадр (preview)' };
    }
  }

  if (sourcePath) {
    const base64 = await fetchVideoFrameBase64(sourcePath, playheadSec);
    if (base64) {
      return {
        base64,
        source: 'video-frame',
        label: `кадр видео @ ${playheadSec.toFixed(1)}s`,
      };
    }
  }

  return { base64: null, source: 'none', label: 'не выбран' };
}
