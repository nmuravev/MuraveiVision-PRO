import { useCallback, useEffect, useRef, useState } from 'react';
import { addEvent } from '../debug/sessionTrace';
import { authHeaders } from '../store/useMuraveiStore';

export type HudZones = {
  top: number;
  bottom: number;
  left: number;
  right: number;
  source: string;
  ready: boolean;
};

export function useHudZones(sourcePath: string | null | undefined, enabled: boolean) {
  const [zones, setZones] = useState<HudZones | null>(null);
  const [archiveEnabled, setArchiveEnabled] = useState(true);
  const [liveEnabled, setLiveEnabled] = useState(false);
  const tracedKey = useRef<string>('');

  const refresh = useCallback(async () => {
    if (!sourcePath || !enabled) {
      setZones(null);
      return;
    }
    try {
      const res = await fetch(
        `/api/hud/zones?video_path=${encodeURIComponent(sourcePath)}`,
        { headers: authHeaders() },
      );
      if (!res.ok) return;
      const data = (await res.json()) as {
        zones?: HudZones;
        archive_enabled?: boolean;
        live_enabled?: boolean;
      };
      if (typeof data.archive_enabled === 'boolean') setArchiveEnabled(data.archive_enabled);
      if (typeof data.live_enabled === 'boolean') setLiveEnabled(data.live_enabled);
      const z = data.zones ?? null;
      setZones(z);
      if (z?.ready && (z.top > 0 || z.bottom > 0 || z.left > 0 || z.right > 0)) {
        const key = `${sourcePath}:${z.top}:${z.bottom}:${z.source}`;
        if (tracedKey.current !== key) {
          tracedKey.current = key;
          addEvent('note', 'hud-zones', {
            source: z.source,
            top: z.top,
            bottom: z.bottom,
            left: z.left,
            right: z.right,
          });
        }
      }
    } catch {
      /* ignore */
    }
  }, [sourcePath, enabled]);

  useEffect(() => {
    void refresh();
    if (!sourcePath || !enabled) return;
    const id = window.setInterval(() => {
      void refresh();
    }, 2500);
    return () => window.clearInterval(id);
  }, [sourcePath, enabled, refresh]);

  const saveManual = useCallback(
    async (next: Pick<HudZones, 'top' | 'bottom' | 'left' | 'right'>) => {
      if (!sourcePath) return;
      const res = await fetch('/api/hud/zones', {
        method: 'PUT',
        headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_path: sourcePath, ...next }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as { zones?: HudZones };
      if (data.zones) setZones(data.zones);
    },
    [sourcePath],
  );

  const disableForVideo = useCallback(async () => {
    await saveManual({ top: 0, bottom: 0, left: 0, right: 0 });
  }, [saveManual]);

  return {
    zones,
    archiveEnabled,
    liveEnabled,
    refresh,
    saveManual,
    disableForVideo,
  };
}
