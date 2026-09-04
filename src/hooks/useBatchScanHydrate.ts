import { useEffect } from 'react';
import { useMuraveiStore } from '../store/useMuraveiStore';

const VIDEO_EXT = /\.(mp4|webm|mov|avi|mkv)$/i;

/** Load persisted detections when archive video opens — no auto batch scan. */
export function useBatchScanHydrate(sourcePath: string | undefined, isAuthenticated: boolean): void {
  const hydrateDetections = useMuraveiStore((s) => s.hydrateDetections);

  useEffect(() => {
    if (!isAuthenticated || !sourcePath || !VIDEO_EXT.test(sourcePath)) return;
    void hydrateDetections(sourcePath);
  }, [sourcePath, isAuthenticated, hydrateDetections]);
}
