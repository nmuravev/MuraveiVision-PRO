import React, { useCallback, useEffect, useState } from 'react';
import { authHeaders, useMuraveiStore } from '../../store/useMuraveiStore';

type HardwarePayload = {
  gpu_name?: string;
  vram_total_gb?: number;
  vram_used_gb?: number;
  vram_free_gb?: number;
};

function toneClass(freeGb: number, totalGb: number): string {
  if (totalGb <= 0) return 'text-dv-muted';
  if (freeGb > 3) return 'text-emerald-400';
  if (freeGb >= 1) return 'text-amber-400';
  return 'text-dv-danger';
}

export const VramIndicator: React.FC = () => {
  const isAuthenticated = useMuraveiStore((s) => s.isAuthenticated);
  const [hw, setHw] = useState<HardwarePayload | null>(null);

  const fetchVram = useCallback(async () => {
    if (!isAuthenticated) return;
    try {
      const res = await fetch('/api/system/hardware', { headers: authHeaders() });
      if (!res.ok) return;
      const data = (await res.json()) as HardwarePayload;
      setHw(data);
    } catch {
      /* ignore transient errors */
    }
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setHw(null);
      return;
    }
    void fetchVram();
    const interval = setInterval(() => {
      void fetchVram();
    }, 5000);
    return () => clearInterval(interval);
  }, [isAuthenticated, fetchVram]);

  if (!isAuthenticated || !hw) return null;

  const total = Number(hw.vram_total_gb ?? 0);
  const used = Number(hw.vram_used_gb ?? 0);
  const free = Number(hw.vram_free_gb ?? 0);
  const label =
    total <= 0
      ? `VRAM: — (${hw.gpu_name || 'CPU'})`
      : `VRAM: ${used.toFixed(1)}/${total.toFixed(1)} ГБ`;

  return (
    <span
      className={`text-[10px] font-mono tabular-nums shrink-0 max-w-[160px] truncate ${toneClass(free, total)}`}
      title={`${hw.gpu_name || 'GPU'} · свободно ${free.toFixed(1)} ГБ · обновление каждые 5 с`}
      data-testid="vram-indicator"
    >
      {label}
    </span>
  );
};

export default VramIndicator;
