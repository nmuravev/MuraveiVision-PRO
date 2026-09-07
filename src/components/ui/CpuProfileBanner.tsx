import React, { useCallback, useEffect, useState } from 'react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { addEvent } from '../../debug/sessionTrace';

type HardwarePayload = {
  accelerator_kind?: string;
  cpu_profile?: boolean;
  banner?: string;
  directml_available?: boolean;
  system_badge_ru?: string;
  portable_mismatch?: { level?: string; message_ru?: string } | null;
};

/**
 * Non-blocking banner: portable build/tier badge + CPU profile when no CUDA.
 */
export const CpuProfileBanner: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [banner, setBanner] = useState<string>('');
  const [badge, setBadge] = useState<string>('');
  const [logged, setLogged] = useState(false);

  const fetchHw = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/system/hardware', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as HardwarePayload;
      if (data.system_badge_ru) {
        setBadge(data.system_badge_ru);
      }
      const mismatch = data.portable_mismatch?.message_ru;
      if (data.cpu_profile || data.accelerator_kind === 'cpu') {
        const text =
          mismatch ||
          data.banner ||
          'Нет NVIDIA GPU — режим CPU + DirectML (если доступен)';
        setBanner(text);
        if (!logged) {
          addEvent('note', `accelerator profile: cpu`, {
            accelerator_kind: data.accelerator_kind,
            directml_available: data.directml_available,
            system_badge_ru: data.system_badge_ru,
          });
          setLogged(true);
        }
      } else {
        setBanner(mismatch || '');
        if (!logged && data.accelerator_kind === 'cuda') {
          addEvent('note', `accelerator profile: cuda`, {
            accelerator_kind: 'cuda',
            system_badge_ru: data.system_badge_ru,
          });
          setLogged(true);
        }
      }
    } catch {
      /* ignore */
    }
  }, [isAuthenticated, logged]);

  useEffect(() => {
    if (!isAuthenticated) {
      setBanner('');
      setBadge('');
      setLogged(false);
      return;
    }
    void fetchHw();
  }, [isAuthenticated, fetchHw]);

  if (!banner && !badge) return null;

  return (
    <div
      className="px-3 py-1.5 text-[11px] text-amber-200/95 bg-amber-950/40 border-b border-amber-800/40 text-center"
      data-testid="cpu-profile-banner"
      role="status"
    >
      {badge ? <span data-testid="system-build-badge">{badge}</span> : null}
      {badge && banner ? <span className="mx-2 opacity-50">·</span> : null}
      {banner ? <span>{banner}</span> : null}
    </div>
  );
};

export default CpuProfileBanner;
