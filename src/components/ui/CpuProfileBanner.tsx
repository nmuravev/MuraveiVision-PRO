import React, { useCallback, useEffect, useState } from 'react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';
import { addEvent } from '../../debug/sessionTrace';

type HardwarePayload = {
  accelerator_kind?: string;
  cpu_profile?: boolean;
  banner?: string;
  directml_available?: boolean;
};

/**
 * Non-blocking banner when NVIDIA CUDA is absent (CPU + optional DirectML).
 */
export const CpuProfileBanner: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [banner, setBanner] = useState<string>('');
  const [logged, setLogged] = useState(false);

  const fetchHw = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/system/hardware', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as HardwarePayload;
      if (data.cpu_profile || data.accelerator_kind === 'cpu') {
        const text =
          data.banner ||
          'Нет NVIDIA GPU — режим CPU + DirectML (если доступен)';
        setBanner(text);
        if (!logged) {
          addEvent('note', `accelerator profile: cpu`, {
            accelerator_kind: data.accelerator_kind,
            directml_available: data.directml_available,
          });
          setLogged(true);
        }
      } else {
        setBanner('');
        if (!logged && data.accelerator_kind === 'cuda') {
          addEvent('note', `accelerator profile: cuda`, {
            accelerator_kind: 'cuda',
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
      setLogged(false);
      return;
    }
    void fetchHw();
  }, [isAuthenticated, fetchHw]);

  if (!banner) return null;

  return (
    <div
      className="px-3 py-1.5 text-[11px] text-amber-200/95 bg-amber-950/40 border-b border-amber-800/40 text-center"
      data-testid="cpu-profile-banner"
      role="status"
    >
      {banner}
    </div>
  );
};

export default CpuProfileBanner;
