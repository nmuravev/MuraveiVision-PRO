import { useEffect, useRef } from 'react';
import { mediaPathsMatch } from '../lib/mediaPaths';
import { useBatchScanStore } from '../store/useBatchScanStore';
import { useMuraveiStore } from '../store/useMuraveiStore';
import type { PersistedDetection } from '../types/muravei';

const VIDEO_EXT = /\.(mp4|webm|mov|avi|mkv)$/i;

function hasBatchScanDetections(detections: PersistedDetection[], sourcePath: string): boolean {
  return detections.some(
    (d) =>
      !d.is_deleted &&
      d.origin === 'batch_scan' &&
      mediaPathsMatch(d.source_video || '', sourcePath),
  );
}

export function useAutoBatchScan(sourcePath: string | undefined, isAuthenticated: boolean): void {
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);
  const startScan = useBatchScanStore((s) => s.startScan);
  const scanStatus = useBatchScanStore((s) => s.status);
  const scanVideoPath = useBatchScanStore((s) => s.videoPath);
  const lastAttemptRef = useRef<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !sourcePath || !VIDEO_EXT.test(sourcePath)) return;

    if (scanStatus === 'running' && scanVideoPath && mediaPathsMatch(scanVideoPath, sourcePath)) {
      return;
    }
    // One auto-attempt per source path — idle/error must not reconnect-spam SSE.
    if (lastAttemptRef.current === sourcePath) {
      return;
    }

    let cancelled = false;

    void (async () => {
      await hydrateDetections(sourcePath);
      if (cancelled) return;

      const detections = useMuraveiStore.getState().detections;
      if (hasBatchScanDetections(detections, sourcePath)) {
        lastAttemptRef.current = sourcePath;
        return;
      }

      lastAttemptRef.current = sourcePath;
      try {
        await startScan(sourcePath, hydrateDetections);
      } catch {
        /* errors surfaced via batch scan store */
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [sourcePath, isAuthenticated, hydrateDetections, startScan, scanStatus, scanVideoPath]);
}
