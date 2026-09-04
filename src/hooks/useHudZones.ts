import { useCallback, useEffect, useRef, useState } from 'react';
import { addEvent } from '../debug/sessionTrace';
import { SILENT_API_ERROR_HEADER } from '../lib/apiError';
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
  const [apiMissing, setApiMissing] = useState(false);
  const tracedKey = useRef<string>('');

  const refresh = useCallback(async (): Promise<'ok' | 'pending' | 'ready' | 'missing' | 'idle'> => {
    if (!sourcePath || !enabled) {
      setZones(null);
      return 'idle';
    }
    try {
      const res = await fetch(
        `/api/hud/zones?video_path=${encodeURIComponent(sourcePath)}`,
        {
          headers: {
            ...authHeaders(),
            [SILENT_API_ERROR_HEADER]: '1',
          },
        },
      );
      if (res.status === 404) {
        setApiMissing(true);
        setZones(null);
        return 'missing';
      }
      if (!res.ok) return 'idle';
      setApiMissing(false);
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
      if (!z) return 'idle';
      if (!z.ready || z.source === 'pending') return 'pending';
      return 'ready';
    } catch {
      return 'idle';
    }
  }, [sourcePath, enabled]);

  useEffect(() => {
    setApiMissing(false);
    tracedKey.current = '';
    let cancelled = false;
    let timer: number | undefined;

    const tick = async () => {
      const status = await refresh();
      if (cancelled) return;
      if (status === 'pending') {
        timer = window.setTimeout(() => {
          void tick();
        }, 2500);
      }
      // ready | missing | idle → stop polling
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [sourcePath, enabled, refresh]);

  const saveManual = useCallback(
    async (next: Pick<HudZones, 'top' | 'bottom' | 'left' | 'right'>) => {
      if (!sourcePath || apiMissing) return;
      const res = await fetch('/api/hud/zones', {
        method: 'PUT',
        headers: {
          ...authHeaders(),
          'Content-Type': 'application/json',
          [SILENT_API_ERROR_HEADER]: '1',
        },
        body: JSON.stringify({ video_path: sourcePath, ...next }),
      });
      if (!res.ok) return;
      const data = (await res.json()) as { zones?: HudZones };
      if (data.zones) setZones(data.zones);
    },
    [sourcePath, apiMissing],
  );

  const disableForVideo = useCallback(async () => {
    await saveManual({ top: 0, bottom: 0, left: 0, right: 0 });
  }, [saveManual]);

  return {
    zones,
    archiveEnabled,
    liveEnabled,
    apiMissing,
    refresh,
    saveManual,
    disableForVideo,
  };
}
